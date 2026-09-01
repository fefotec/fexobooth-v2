// FexoNikonBridge — unsichtbarer Nikon-Tethering-Prozess für FexoBooth V2.
//
// Steuert Nikon-DSLRs (getestet werden soll: D3300) über rohes PTP/MTP via
// Windows-WPD-API. Motor ist CameraControl.Devices (Kern von digiCamControl,
// MIT-Lizenz). Es wird KEIN Fenster geöffnet; FexoBooth startet den Prozess
// mit CREATE_NO_WINDOW und spricht ihn über stdin/stdout an.
//
// Protokoll (eine Anfrage gleichzeitig, JSON-Zeilen):
//   stdin : {"id": 1, "cmd": "ping"}\n
//   stdout: {"id": 1, "ok": true, ...}\n
//   Binärantworten (JPEG): Header-Zeile mit "len", direkt danach len Rohbytes.
// Kommandos: ping, diag, list, init, lv_start, lv_stop, frame, capture, release, quit

using System;
using System.ComponentModel;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using CameraControl.Devices;
using CameraControl.Devices.Classes;
using Newtonsoft.Json.Linq;

namespace FexoNikonBridge
{
    internal static class Program
    {
        private const string BridgeVersion = "0.2.0";

        private static Stream _stdout;
        private static readonly object OutLock = new object();
        private static readonly BoundedLineTextWriter LibraryOutput = new BoundedLineTextWriter(100, 64000, 1024);
        private static readonly BoundedLineTextWriter LibraryErrors = new BoundedLineTextWriter(40, 32000, 1024);
        private static bool _diagnosticsEnabled;

        private static CameraDeviceManager _deviceManager;
        private static ICameraDevice _camera;

        // Rein beobachtender Diagnosezustand. `diag` liest nur diese Felder und
        // die bereits vorhandene ConnectedDevices-Liste; es startet niemals
        // selbst einen Scan oder eine Kameraaktion.
        private static readonly object DiagnosticLock = new object();
        private static DateTime? _lastScanStartedUtc;
        private static DateTime? _lastScanFinishedUtc;
        private static long? _lastScanDurationMs;
        private static string _lastScanReason;
        private static string _lastScanResult;
        private static bool? _lastScanReturnValue;
        private static int? _lastScanDeviceCount;
        private static int? _lastScanConnectedCount;
        private static JObject _lastException;
        private static DateTime? _lastInitAttemptUtc;
        private static DateTime? _lastSuccessfulInitUtc;
        private static string _lastInitResult;

        // Capture-Synchronisation: PhotoCaptured-Event liefert das Bild auf
        // einem fremden Thread; das capture-Kommando wartet hier darauf.
        private static readonly ManualResetEventSlim PhotoReady = new ManualResetEventSlim(false);
        private static byte[] _lastPhoto;
        private static readonly object PhotoLock = new object();

        // Bewusst MTA (kein [STAThread]): Main blockiert in stdin.ReadLine ohne
        // Message-Pump — in einer STA würde das COM-Marshaling zum WPD-Objekt
        // (Nikon-Event-Polling von Timer-/Transfer-Threads) verhungern. digiCamControl
        // selbst spricht die Kameras ebenfalls aus MTA-Threads an.
        [MTAThread]
        private static int Main(string[] args)
        {
            // Roh-Handle für UNSER Protokoll sichern, dann Console.Out vom
            // Protokoll trennen: CameraControl.Devices schreibt sonst Banner wie
            // "**CRITICAL ERROR** ... EDSDK.dll is missing" mitten in den
            // JSON/Binär-Strom (real beobachtet) und könnte einen laufenden
            // Frame-Payload korrumpieren. Die letzten begrenzten Zeilen bleiben
            // nun ausschließlich für das read-only `diag`-Kommando erhalten.
            _stdout = Console.OpenStandardOutput();
            _diagnosticsEnabled = HasArgument(args, "--developer-diagnostics");
            if (_diagnosticsEnabled)
            {
                Console.SetOut(LibraryOutput);
                Console.SetError(LibraryOutput);
                InstallLibraryDiagnostics();
            }
            else
            {
                // Exakt der bisherige Produktionspfad: Fremdausgaben verwerfen.
                Console.SetOut(TextWriter.Null);
            }
            var stdin = new StreamReader(Console.OpenStandardInput(), new UTF8Encoding(false));

            string line;
            while ((line = stdin.ReadLine()) != null)
            {
                long id = 0;
                string cmd = "";
                try
                {
                    var request = JObject.Parse(line);
                    id = request.Value<long?>("id") ?? 0;
                    cmd = (request.Value<string>("cmd") ?? "").Trim().ToLowerInvariant();

                    switch (cmd)
                    {
                        case "ping":
                            Reply(id, new JObject { ["bridge"] = "FexoNikonBridge", ["version"] = BridgeVersion });
                            break;
                        case "diag":
                            HandleDiagnostics(id);
                            break;
                        case "list":
                            HandleList(id);
                            break;
                        case "init":
                            HandleInit(id, request);
                            break;
                        case "lv_start":
                            RequireCamera().StartLiveView();
                            Reply(id);
                            break;
                        case "lv_stop":
                            RequireCamera().StopLiveView();
                            Reply(id);
                            break;
                        case "frame":
                            HandleFrame(id);
                            break;
                        case "capture":
                            HandleCapture(id, request.Value<double?>("timeout") ?? 10.0);
                            break;
                        case "release":
                            HandleRelease(id);
                            break;
                        case "quit":
                            Reply(id);
                            Cleanup();
                            return 0;
                        default:
                            ReplyError(id, "Unbekanntes Kommando: " + cmd);
                            break;
                    }
                }
                catch (Exception ex)
                {
                    if (_diagnosticsEnabled && cmd == "init")
                    {
                        lock (DiagnosticLock)
                        {
                            _lastInitResult = "exception";
                        }
                    }
                    RecordException("command:" + (string.IsNullOrEmpty(cmd) ? "parse" : cmd), ex);
                    ReplyError(id, ex.Message);
                }
            }

            Cleanup();
            return 0;
        }

        private static bool HasArgument(string[] args, string expected)
        {
            if (args == null)
            {
                return false;
            }
            foreach (var argument in args)
            {
                if (string.Equals(argument, expected, StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
            return false;
        }

        private static void InstallLibraryDiagnostics()
        {
            // CameraControl.Devices verschluckt zentrale WPD-/WIA-Ausnahmen
            // intern und reicht sie nur über diese Events weiter. Jeder Handler
            // ist deshalb strikt never-throw: Ein Diagnosefehler darf niemals
            // den Scan-Thread der Fremdbibliothek beeinflussen.
            CameraControl.Devices.Log.LogError += OnLibraryLogError;
            CameraControl.Devices.Log.LogDebug += OnLibraryLogDebug;
            CameraControl.Devices.Log.LogInfo += OnLibraryLogInfo;
        }

        private static void OnLibraryLogError(LogEventArgs e)
        {
            SafeCaptureLibraryLog("error", e);
        }

        private static void OnLibraryLogDebug(LogEventArgs e)
        {
            SafeCaptureLibraryLog("debug", e);
        }

        private static void OnLibraryLogInfo(LogEventArgs e)
        {
            SafeCaptureLibraryLog("info", e);
        }

        private static void SafeCaptureLibraryLog(string level, LogEventArgs e)
        {
            try
            {
                var message = e == null || e.Message == null ? "" : e.Message.ToString();
                var exception = e == null ? null : e.Exception;
                if (IsExpectedCanonSdkNoise(message, exception) || IsKnownLibraryNoise(message))
                {
                    return;
                }
                var line = "library:" + level + " " + (message ?? "");
                if (exception != null)
                {
                    line += " | " + exception.GetType().FullName + ": " + exception.Message;
                }
                LibraryOutput.AppendLine(line);
                if (exception != null || string.Equals(level, "error", StringComparison.OrdinalIgnoreCase))
                {
                    LibraryErrors.AppendLine(line);
                }
                if (exception != null)
                {
                    RecordException("library:" + level, exception);
                }
            }
            catch
            {
                // Niemals in CameraControl.Devices zurückwerfen.
            }
        }

        private static bool IsKnownLibraryNoise(string message)
        {
            try
            {
                if (string.Equals((message ?? "").Trim(), "Wia initialized", StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
                if (!string.IsNullOrEmpty(message)
                    && message.StartsWith("Connection device", StringComparison.OrdinalIgnoreCase))
                {
                    return message.IndexOf("Nikon", StringComparison.OrdinalIgnoreCase) < 0
                        && message.IndexOf("D3300", StringComparison.OrdinalIgnoreCase) < 0
                        && message.IndexOf("VID_04B0", StringComparison.OrdinalIgnoreCase) < 0;
                }
            }
            catch
            {
                return false;
            }
            return false;
        }

        private static bool IsExpectedCanonSdkNoise(string message, Exception exception)
        {
            try
            {
                var exceptionType = exception == null ? "" : exception.GetType().FullName ?? "";
                return exceptionType.StartsWith("Canon.Eos.", StringComparison.OrdinalIgnoreCase)
                    || (!string.IsNullOrEmpty(message)
                        && message.IndexOf("canon driver", StringComparison.OrdinalIgnoreCase) >= 0);
            }
            catch
            {
                return false;
            }
        }

        // ------------------------------------------------------------------
        // Kommandos
        // ------------------------------------------------------------------

        private static DateTime _lastScanUtc = DateTime.MinValue;

        private static void EnsureDeviceManager()
        {
            if (_deviceManager != null)
            {
                return;
            }
            _deviceManager = new CameraDeviceManager();
            // Tablet-eigene Webcams dürfen NIE als "Nikon" gebunden werden.
            _deviceManager.DetectWebcams = false;
            _deviceManager.PhotoCaptured += OnPhotoCaptured;
            RunScan("manager_create");
            _lastScanUtc = DateTime.UtcNow;
        }

        private static void RescanThrottled()
        {
            // Hot-Plug: Kamera kann NACH dem Bridge-Start eingeschaltet/angesteckt
            // werden. ConnectToCamera() erneut aufrufen, aber gedrosselt (~3s),
            // damit der sekündliche Status-Check der App keinen Scan-Sturm auslöst.
            if ((DateTime.UtcNow - _lastScanUtc).TotalSeconds < 3)
            {
                return;
            }
            _lastScanUtc = DateTime.UtcNow;
            RunScan("list_rescan");
        }

        private static bool RunScan(string reason)
        {
            if (!_diagnosticsEnabled)
            {
                return _deviceManager.ConnectToCamera();
            }
            // Nur Messung um den bereits vorhandenen ConnectToCamera-Aufruf.
            // Die drei Aufrufer behalten ihre bisherigen _lastScanUtc-
            // Zuweisungen, damit das Throttling semantisch unverändert bleibt.
            var startedUtc = DateTime.UtcNow;
            var stopwatch = Stopwatch.StartNew();
            lock (DiagnosticLock)
            {
                _lastScanStartedUtc = startedUtc;
                _lastScanFinishedUtc = null;
                _lastScanDurationMs = null;
                _lastScanReason = reason;
                _lastScanResult = "running";
                _lastScanReturnValue = null;
                _lastScanDeviceCount = null;
                _lastScanConnectedCount = null;
            }

            try
            {
                var returnValue = _deviceManager.ConnectToCamera();
                int deviceCount;
                int connectedCount;
                CountKnownDevices(out deviceCount, out connectedCount);
                lock (DiagnosticLock)
                {
                    _lastScanResult = "completed";
                    _lastScanReturnValue = returnValue;
                    _lastScanDeviceCount = deviceCount;
                    _lastScanConnectedCount = connectedCount;
                }
                return returnValue;
            }
            catch (Exception ex)
            {
                lock (DiagnosticLock)
                {
                    _lastScanResult = "exception";
                }
                RecordException("scan:" + reason, ex);
                throw;
            }
            finally
            {
                stopwatch.Stop();
                lock (DiagnosticLock)
                {
                    _lastScanFinishedUtc = DateTime.UtcNow;
                    _lastScanDurationMs = stopwatch.ElapsedMilliseconds;
                }
            }
        }

        private static void CountKnownDevices(out int deviceCount, out int connectedCount)
        {
            deviceCount = 0;
            connectedCount = 0;
            try
            {
                foreach (var device in _deviceManager.ConnectedDevices)
                {
                    deviceCount++;
                    try
                    {
                        if (device != null && device.IsConnected)
                        {
                            connectedCount++;
                        }
                    }
                    catch
                    {
                        // Diagnose darf den erfolgreichen Scan nie verändern.
                    }
                    if (deviceCount >= 64)
                    {
                        break;
                    }
                }
            }
            catch
            {
                // Eine parallele Library-Aktualisierung ist nur Diagnoseverlust.
                deviceCount = -1;
                connectedCount = -1;
            }
        }

        private static ICameraDevice FindRealCamera()
        {
            foreach (var device in _deviceManager.ConnectedDevices)
            {
                if (device == null || !device.IsConnected)
                {
                    continue;
                }
                // Defensiv: Webcam-Geräteklassen aussortieren, falls doch welche
                // in der Liste landen (Typname statt Namespace-Referenz, damit
                // der Check nicht an einer Library-Version hängt).
                if (device.GetType().Name.IndexOf("WebCamera", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    continue;
                }
                return device;
            }
            return null;
        }

        private static void HandleList(long id)
        {
            EnsureDeviceManager();
            if (FindRealCamera() == null)
            {
                RescanThrottled();
            }
            var cameras = new JArray();
            foreach (var device in _deviceManager.ConnectedDevices)
            {
                if (device == null || !device.IsConnected)
                {
                    continue;
                }
                if (device.GetType().Name.IndexOf("WebCamera", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    continue;
                }
                cameras.Add(new JObject
                {
                    ["name"] = device.DeviceName ?? "Unbekannte Kamera",
                    ["serial"] = device.SerialNumber ?? device.DeviceName ?? "",
                });
            }
            Reply(id, new JObject { ["cameras"] = cameras });
        }

        private static void HandleDiagnostics(long id)
        {
            // WICHTIG: Kein EnsureDeviceManager(), kein ConnectToCamera(). Dieser
            // Snapshot liest nur bereits vorhandenen Zustand.
            DateTime? scanStarted;
            DateTime? scanFinished;
            long? scanDuration;
            string scanReason;
            string scanResult;
            bool? scanReturnValue;
            int? scanDeviceCount;
            int? scanConnectedCount;
            JObject lastException;
            DateTime? initAttempt;
            DateTime? successfulInit;
            string initResult;

            lock (DiagnosticLock)
            {
                scanStarted = _lastScanStartedUtc;
                scanFinished = _lastScanFinishedUtc;
                scanDuration = _lastScanDurationMs;
                scanReason = _lastScanReason;
                scanResult = _lastScanResult;
                scanReturnValue = _lastScanReturnValue;
                scanDeviceCount = _lastScanDeviceCount;
                scanConnectedCount = _lastScanConnectedCount;
                lastException = _lastException == null ? null : (JObject)_lastException.DeepClone();
                initAttempt = _lastInitAttemptUtc;
                successfulInit = _lastSuccessfulInitUtc;
                initResult = _lastInitResult;
            }

            string deviceSnapshotError;
            var devices = BuildDeviceSnapshot(out deviceSnapshotError);
            var cameraSnapshot = BuildCurrentCameraSnapshot();
            var cameraInitialized = cameraSnapshot != null && cameraSnapshot.Value<bool?>("is_connected") == true;
            var processId = Process.GetCurrentProcess().Id;

            var scan = new JObject
            {
                ["started_utc"] = DateToken(scanStarted),
                ["finished_utc"] = DateToken(scanFinished),
                ["duration_ms"] = NumberToken(scanDuration),
                ["reason"] = StringToken(scanReason),
                ["result"] = StringToken(scanResult),
                ["return_value"] = BoolToken(scanReturnValue),
                ["device_count"] = NumberToken(scanDeviceCount),
                ["connected_count"] = NumberToken(scanConnectedCount),
            };

            var diagnostics = new JObject
            {
                ["bridge_version"] = BridgeVersion,
                ["pid"] = processId,
                ["developer_diagnostics_enabled"] = _diagnosticsEnabled,
                ["manager_created"] = _deviceManager != null,
                ["camera_initialized"] = cameraInitialized,
                ["camera"] = (JToken)cameraSnapshot ?? JValue.CreateNull(),
                ["last_scan"] = scan,
                ["last_init_attempt_utc"] = DateToken(initAttempt),
                ["last_successful_init_utc"] = DateToken(successfulInit),
                ["last_init_result"] = StringToken(initResult),
                ["connected_devices"] = devices,
                ["device_snapshot_error"] = StringToken(deviceSnapshotError),
                ["library_output"] = new JArray(LibraryOutput.Snapshot()),
                ["library_errors"] = new JArray(LibraryErrors.Snapshot()),
                ["last_exception"] = (JToken)lastException ?? JValue.CreateNull(),
            };
            Reply(id, new JObject { ["diagnostics"] = diagnostics });
        }

        private static JArray BuildDeviceSnapshot(out string snapshotError)
        {
            var result = new JArray();
            snapshotError = null;
            if (_deviceManager == null)
            {
                return result;
            }

            try
            {
                var index = 0;
                foreach (var device in _deviceManager.ConnectedDevices)
                {
                    if (index >= 32)
                    {
                        snapshotError = "device_limit_reached";
                        break;
                    }

                    var entry = new JObject { ["index"] = index };
                    var propertyErrors = new List<string>();
                    if (device == null)
                    {
                        entry["null_device"] = true;
                    }
                    else
                    {
                        AddSafeDeviceValue(entry, "type", () => device.GetType().FullName, propertyErrors);
                        AddSafeDeviceValue(entry, "name", () => device.DeviceName, propertyErrors);
                        AddSafeDeviceValue(entry, "manufacturer", () => device.Manufacturer, propertyErrors);
                        AddSafeDeviceValue(entry, "serial", () => device.SerialNumber, propertyErrors);
                        AddSafeDeviceValue(entry, "port", () => device.PortName, propertyErrors);
                        AddSafeDeviceValue(entry, "is_connected", () => device.IsConnected, propertyErrors);
                        AddSafeDeviceValue(entry, "is_busy", () => device.IsBusy, propertyErrors);
                    }
                    if (propertyErrors.Count > 0)
                    {
                        entry["property_errors"] = new JArray(propertyErrors);
                    }
                    result.Add(entry);
                    index++;
                }
            }
            catch (Exception ex)
            {
                snapshotError = Truncate(ex.GetType().Name + ": " + ex.Message, 300);
            }
            return result;
        }

        private static JObject BuildCurrentCameraSnapshot()
        {
            var camera = _camera;
            if (camera == null)
            {
                return null;
            }
            var entry = new JObject();
            var propertyErrors = new List<string>();
            AddSafeDeviceValue(entry, "type", () => camera.GetType().FullName, propertyErrors);
            AddSafeDeviceValue(entry, "name", () => camera.DeviceName, propertyErrors);
            AddSafeDeviceValue(entry, "serial", () => camera.SerialNumber, propertyErrors);
            AddSafeDeviceValue(entry, "is_connected", () => camera.IsConnected, propertyErrors);
            AddSafeDeviceValue(entry, "is_busy", () => camera.IsBusy, propertyErrors);
            if (propertyErrors.Count > 0)
            {
                entry["property_errors"] = new JArray(propertyErrors);
            }
            return entry;
        }

        private static void AddSafeDeviceValue(
            JObject target,
            string key,
            Func<object> getter,
            List<string> errors)
        {
            try
            {
                var value = getter();
                target[key] = value == null ? JValue.CreateNull() : JToken.FromObject(value);
            }
            catch (Exception ex)
            {
                target[key] = JValue.CreateNull();
                errors.Add(key + ":" + Truncate(ex.GetType().Name + ": " + ex.Message, 160));
            }
        }

        private static void HandleInit(long id, JObject request)
        {
            EnsureDeviceManager();
            if (_diagnosticsEnabled)
            {
                lock (DiagnosticLock)
                {
                    _lastInitAttemptUtc = DateTime.UtcNow;
                    _lastInitResult = "searching";
                }
            }

            // Kamera-Erkennung kann nach ConnectToCamera() einen Moment dauern.
            // Bewusst NICHT blind SelectedCameraDevice nehmen (könnte ein
            // Platzhalter/Fremdgerät sein), sondern gezielt eine echte Kamera.
            var deadline = DateTime.UtcNow.AddSeconds(15);
            ICameraDevice camera = FindRealCamera();
            while (camera == null)
            {
                if (DateTime.UtcNow > deadline)
                {
                    if (_diagnosticsEnabled)
                    {
                        lock (DiagnosticLock)
                        {
                            _lastInitResult = "no_camera_timeout";
                        }
                    }
                    ReplyError(id, "Keine Nikon-Kamera gefunden (USB/PTP prüfen)");
                    return;
                }
                Thread.Sleep(250);
                RunScan("init_retry");
                _lastScanUtc = DateTime.UtcNow;
                camera = FindRealCamera();
            }

            _camera = camera;
            // Bild direkt in den RAM statt auf die SD-Karte übertragen.
            _camera.CaptureInSdRam = true;

            // JPEG-Größe an der Kamera setzen (Standard "M": D3300 = 4496x3000
            // statt 6000x4000) — reicht für den 1800x1200-Druck locker und
            // verkürzt den USB-Transfer pro Foto deutlich.
            var imageSize = TrySetImageSize(_camera, request.Value<string>("size"));

            var reply = new JObject { ["camera"] = _camera.DeviceName ?? "Nikon" };
            if (imageSize != null)
            {
                reply["image_size"] = imageSize;
            }
            if (_diagnosticsEnabled)
            {
                lock (DiagnosticLock)
                {
                    _lastSuccessfulInitUtc = DateTime.UtcNow;
                    _lastInitResult = "success";
                }
            }
            Reply(id, reply);
        }

        private static string TrySetImageSize(ICameraDevice camera, string sizeWish)
        {
            // Best-effort: Die "Image Size"-Property (PTP 0x5003) liegt in den
            // AdvancedProperties; fehlt sie oder passt etwas nicht, bleibt die
            // Kamera-Einstellung unangetastet — init darf daran NIE scheitern.
            try
            {
                if (string.IsNullOrEmpty(sizeWish))
                {
                    return null;
                }
                var wish = sizeWish.Trim().ToUpperInvariant();
                if (wish != "L" && wish != "M" && wish != "S")
                {
                    return null;
                }

                foreach (var prop in camera.AdvancedProperties)
                {
                    if (prop == null || prop.Name == null ||
                        !prop.Name.Equals("Image Size", StringComparison.OrdinalIgnoreCase))
                    {
                        continue;
                    }

                    // Kamera liefert Strings wie "6000x4000" — nach Breite
                    // absteigend sortieren: L = größte, M = zweitgrößte, S = kleinste.
                    var widths = new List<long>();
                    var byWidth = new List<string>();
                    foreach (var value in prop.Values)
                    {
                        if (string.IsNullOrEmpty(value))
                        {
                            continue;
                        }
                        int digitEnd = 0;
                        while (digitEnd < value.Length && char.IsDigit(value[digitEnd]))
                        {
                            digitEnd++;
                        }
                        long width;
                        if (digitEnd > 0 && long.TryParse(value.Substring(0, digitEnd), out width) && width > 0)
                        {
                            int pos = 0;
                            while (pos < widths.Count && widths[pos] > width)
                            {
                                pos++;
                            }
                            widths.Insert(pos, width);
                            byWidth.Insert(pos, value);
                        }
                    }
                    if (byWidth.Count == 0)
                    {
                        return null;
                    }

                    string target;
                    if (wish == "L")
                    {
                        target = byWidth[0];
                    }
                    else if (wish == "S")
                    {
                        target = byWidth[byWidth.Count - 1];
                    }
                    else
                    {
                        target = byWidth[Math.Min(1, byWidth.Count - 1)];
                    }

                    if (target != prop.Value)
                    {
                        prop.SetValue(target);
                    }
                    // PTP-Strings der Kamera enden teils mit \0 — fürs Log/JSON säubern
                    // (SetValue oben braucht den ORIGINAL-String für den Werte-Abgleich).
                    return target.Trim('\0', ' ');
                }
            }
            catch
            {
                // Bildgröße ist Komfort, kein Muss.
            }
            return null;
        }

        private static void HandleFrame(long id)
        {
            var camera = RequireCamera();
            LiveViewData liveView = camera.GetLiveViewImage();
            if (liveView?.ImageData == null || liveView.ImageData.Length <= liveView.ImageDataPosition)
            {
                ReplyError(id, "Kein LiveView-Bild verfügbar");
                return;
            }

            var length = liveView.ImageData.Length - liveView.ImageDataPosition;
            ReplyBinary(id, liveView.ImageData, liveView.ImageDataPosition, length);
        }

        private static void HandleCapture(long id, double timeoutSeconds)
        {
            var camera = RequireCamera();

            lock (PhotoLock)
            {
                _lastPhoto = null;
            }
            PhotoReady.Reset();

            // LiveView vor dem Auslösen stoppen (echte Aufnahme, wie bei Canon).
            try { camera.StopLiveView(); } catch { /* Kamera war ggf. nicht im LiveView */ }

            try
            {
                camera.CapturePhoto();
            }
            catch (DeviceException)
            {
                // Typisch: Autofokus findet im dunklen Partyraum kein Ziel
                // (MTP_Out_of_Focus) oder Objektiv steht auf MF. Dann ohne
                // Autofokus auslösen statt die Session scheitern zu lassen.
                camera.CapturePhotoNoAf();
            }

            if (!PhotoReady.Wait(TimeSpan.FromSeconds(Math.Max(1.0, timeoutSeconds))))
            {
                ReplyError(id, "Capture-Timeout: kein Bild von der Kamera empfangen");
                return;
            }

            byte[] photo;
            lock (PhotoLock)
            {
                photo = _lastPhoto;
                _lastPhoto = null;
            }

            if (photo == null || photo.Length == 0)
            {
                ReplyError(id, "Capture fehlgeschlagen: leeres Bild");
                return;
            }
            ReplyBinary(id, photo, 0, photo.Length);
        }

        private static void HandleRelease(long id)
        {
            try
            {
                if (_camera != null)
                {
                    try { _camera.StopLiveView(); } catch { }
                }
            }
            finally
            {
                _camera = null;
            }
            Reply(id);
        }

        private static void OnPhotoCaptured(object sender, PhotoCapturedEventArgs eventArgs)
        {
            if (eventArgs == null)
            {
                return;
            }
            // Transfer in eigenem Thread — den Event-Thread der Bibliothek nicht
            // blockieren (Vorgabe aus dem offiziellen CameraControl.Devices-Beispiel).
            var thread = new Thread(TransferPhoto);
            thread.Start(eventArgs);
        }

        private static void TransferPhoto(object o)
        {
            var eventArgs = o as PhotoCapturedEventArgs;
            if (eventArgs == null)
            {
                return;
            }
            var tempFile = Path.Combine(Path.GetTempPath(), "fexonikon_" + Guid.NewGuid().ToString("N") + ".jpg");
            try
            {
                eventArgs.CameraDevice.TransferFile(eventArgs.Handle, tempFile);
                lock (PhotoLock)
                {
                    _lastPhoto = File.ReadAllBytes(tempFile);
                }
                PhotoReady.Set();
            }
            catch (Exception ex)
            {
                // Fehler beim Transfer: capture-Kommando läuft in den Timeout.
                RecordException("transfer_photo", ex);
            }
            finally
            {
                try { File.Delete(tempFile); } catch { }
                try { eventArgs.CameraDevice.ReleaseResurce(eventArgs.Handle); } catch { }
                eventArgs.CameraDevice.IsBusy = false;
            }
        }

        private static ICameraDevice RequireCamera()
        {
            if (_camera == null || !_camera.IsConnected)
            {
                throw new InvalidOperationException("Kamera nicht initialisiert (erst 'init' senden)");
            }
            return _camera;
        }

        private static void Cleanup()
        {
            try
            {
                if (_camera != null)
                {
                    try { _camera.StopLiveView(); } catch { }
                }
                _deviceManager?.CloseAll();
            }
            catch
            {
                // Beim Beenden nichts mehr erzwingen.
            }
        }

        private static void RecordException(string context, Exception exception)
        {
            if (!_diagnosticsEnabled)
            {
                return;
            }
            try
            {
                var snapshot = ExceptionToJson(context, exception);
                lock (DiagnosticLock)
                {
                    _lastException = snapshot;
                }
            }
            catch
            {
                // Diagnose ist ausnahmslos Best-Effort.
            }
        }

        private static JObject ExceptionToJson(string context, Exception exception)
        {
            if (exception == null)
            {
                return null;
            }
            var result = new JObject
            {
                ["utc"] = DateTime.UtcNow.ToString("O"),
                ["context"] = Truncate(context, 120),
                ["type"] = Truncate(exception.GetType().FullName, 200),
                ["message"] = Truncate(exception.Message, 500),
                ["hresult"] = exception.HResult,
            };
            var nativeCode = FindNativeErrorCode(exception, 0);
            if (nativeCode.HasValue)
            {
                result["windows_error_code"] = nativeCode.Value;
            }
            return result;
        }

        private static long? FindNativeErrorCode(Exception exception, int depth)
        {
            if (exception == null || depth > 8)
            {
                return null;
            }
            var deviceException = exception as DeviceException;
            if (deviceException != null)
            {
                return deviceException.ErrorCode;
            }
            var comException = exception as COMException;
            if (comException != null)
            {
                return comException.ErrorCode;
            }
            var win32Exception = exception as Win32Exception;
            if (win32Exception != null)
            {
                return win32Exception.NativeErrorCode;
            }
            return FindNativeErrorCode(exception.InnerException, depth + 1);
        }

        private static JToken DateToken(DateTime? value)
        {
            return value.HasValue ? new JValue(value.Value.ToString("O")) : JValue.CreateNull();
        }

        private static JToken StringToken(string value)
        {
            return value == null ? JValue.CreateNull() : new JValue(Truncate(value, 500));
        }

        private static JToken NumberToken(long? value)
        {
            return value.HasValue ? new JValue(value.Value) : JValue.CreateNull();
        }

        private static JToken NumberToken(int? value)
        {
            return value.HasValue ? new JValue(value.Value) : JValue.CreateNull();
        }

        private static JToken BoolToken(bool? value)
        {
            return value.HasValue ? new JValue(value.Value) : JValue.CreateNull();
        }

        private static string Truncate(string value, int maximumLength)
        {
            if (string.IsNullOrEmpty(value) || value.Length <= maximumLength)
            {
                return value;
            }
            return value.Substring(0, maximumLength) + "...[truncated]";
        }

        // ------------------------------------------------------------------
        // Antworten (stdout: JSON-Zeile, optional gefolgt von Rohbytes)
        // ------------------------------------------------------------------

        private static void Reply(long id, JObject extra = null)
        {
            var obj = extra ?? new JObject();
            obj["id"] = id;
            obj["ok"] = true;
            WriteLine(obj);
        }

        private static void ReplyError(long id, string message)
        {
            WriteLine(new JObject { ["id"] = id, ["ok"] = false, ["error"] = message ?? "Fehler" });
        }

        private static void ReplyBinary(long id, byte[] data, int offset, int length)
        {
            lock (OutLock)
            {
                var header = new JObject { ["id"] = id, ["ok"] = true, ["len"] = length };
                var headerBytes = Encoding.UTF8.GetBytes(header.ToString(Newtonsoft.Json.Formatting.None) + "\n");
                _stdout.Write(headerBytes, 0, headerBytes.Length);
                _stdout.Write(data, offset, length);
                _stdout.Flush();
            }
        }

        private static void WriteLine(JObject obj)
        {
            lock (OutLock)
            {
                var bytes = Encoding.UTF8.GetBytes(obj.ToString(Newtonsoft.Json.Formatting.None) + "\n");
                _stdout.Write(bytes, 0, bytes.Length);
                _stdout.Flush();
            }
        }

        private sealed class BoundedLineTextWriter : TextWriter
        {
            private readonly object _lock = new object();
            private readonly Queue<string> _lines = new Queue<string>();
            private readonly StringBuilder _pending = new StringBuilder();
            private readonly int _maximumLines;
            private readonly int _maximumCharacters;
            private readonly int _maximumLineLength;
            private int _storedCharacters;
            private bool _pendingTruncated;

            internal BoundedLineTextWriter(int maximumLines, int maximumCharacters, int maximumLineLength)
            {
                _maximumLines = Math.Max(1, maximumLines);
                _maximumCharacters = Math.Max(1024, maximumCharacters);
                _maximumLineLength = Math.Max(80, maximumLineLength);
            }

            public override Encoding Encoding
            {
                get { return Encoding.UTF8; }
            }

            public override void Write(char value)
            {
                try
                {
                    lock (_lock)
                    {
                        AppendCharacter(value);
                    }
                }
                catch
                {
                    // Fremdausgabe darf nie den Bridge-Prozess beeinflussen.
                }
            }

            public override void Write(string value)
            {
                if (value == null)
                {
                    return;
                }
                try
                {
                    lock (_lock)
                    {
                        foreach (var character in value)
                        {
                            AppendCharacter(character);
                        }
                    }
                }
                catch
                {
                    // Best-Effort.
                }
            }

            public override void WriteLine(string value)
            {
                try
                {
                    lock (_lock)
                    {
                        if (value != null)
                        {
                            foreach (var character in value)
                            {
                                AppendCharacter(character);
                            }
                        }
                        AppendCharacter('\n');
                    }
                }
                catch
                {
                    // Best-Effort.
                }
            }

            internal void AppendLine(string value)
            {
                WriteLine(value);
            }

            internal string[] Snapshot()
            {
                try
                {
                    lock (_lock)
                    {
                        var snapshot = new List<string>(_lines);
                        if (_pending.Length > 0 || _pendingTruncated)
                        {
                            snapshot.Add(PendingLine());
                        }
                        return snapshot.ToArray();
                    }
                }
                catch
                {
                    return new string[0];
                }
            }

            private void AppendCharacter(char value)
            {
                if (value == '\r')
                {
                    return;
                }
                if (value == '\n')
                {
                    FlushPending();
                    return;
                }
                if (_pending.Length < _maximumLineLength)
                {
                    _pending.Append(value);
                }
                else
                {
                    _pendingTruncated = true;
                }
            }

            private string PendingLine()
            {
                return _pending.ToString() + (_pendingTruncated ? "...[truncated]" : "");
            }

            private void FlushPending()
            {
                if (_pending.Length == 0 && !_pendingTruncated)
                {
                    return;
                }
                var line = PendingLine();
                _pending.Clear();
                _pendingTruncated = false;
                if (IsExpectedConsoleNoise(line))
                {
                    return;
                }
                _lines.Enqueue(line);
                _storedCharacters += line.Length;
                while (_lines.Count > _maximumLines || _storedCharacters > _maximumCharacters)
                {
                    _storedCharacters -= _lines.Dequeue().Length;
                }
            }

            private static bool IsExpectedConsoleNoise(string line)
            {
                try
                {
                    var value = (line ?? "").Trim();
                    return (value.IndexOf("Failed to initialize", StringComparison.OrdinalIgnoreCase) >= 0
                            && value.IndexOf("SDK", StringComparison.OrdinalIgnoreCase) >= 0)
                        || string.Equals(value, "**CRITICAL ERROR**", StringComparison.OrdinalIgnoreCase)
                        || value.IndexOf(
                            "Canon EOS camera library, EDSDK.dll is missing",
                            StringComparison.OrdinalIgnoreCase) >= 0
                        || value.StartsWith(
                            "Install it after downloading from Canon's site",
                            StringComparison.OrdinalIgnoreCase);
                }
                catch
                {
                    return false;
                }
            }
        }
    }
}
