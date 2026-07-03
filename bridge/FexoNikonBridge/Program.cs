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
// Kommandos: ping, list, init, lv_start, lv_stop, frame, capture, release, quit

using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading;
using CameraControl.Devices;
using CameraControl.Devices.Classes;
using Newtonsoft.Json.Linq;

namespace FexoNikonBridge
{
    internal static class Program
    {
        private const string BridgeVersion = "0.1.0";

        private static Stream _stdout;
        private static readonly object OutLock = new object();

        private static CameraDeviceManager _deviceManager;
        private static ICameraDevice _camera;

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
            // Roh-Handle für UNSER Protokoll sichern, dann Console.Out stumm
            // schalten: CameraControl.Devices schreibt sonst Banner wie
            // "**CRITICAL ERROR** ... EDSDK.dll is missing" mitten in den
            // JSON/Binär-Strom (real beobachtet) und könnte einen laufenden
            // Frame-Payload korrumpieren. Die Library-Ausgaben sind für die
            // Nikon-Steuerung irrelevant.
            _stdout = Console.OpenStandardOutput();
            Console.SetOut(TextWriter.Null);
            var stdin = new StreamReader(Console.OpenStandardInput(), new UTF8Encoding(false));

            string line;
            while ((line = stdin.ReadLine()) != null)
            {
                long id = 0;
                try
                {
                    var request = JObject.Parse(line);
                    id = request.Value<long?>("id") ?? 0;
                    var cmd = (request.Value<string>("cmd") ?? "").Trim().ToLowerInvariant();

                    switch (cmd)
                    {
                        case "ping":
                            Reply(id, new JObject { ["bridge"] = "FexoNikonBridge", ["version"] = BridgeVersion });
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
                    ReplyError(id, ex.Message);
                }
            }

            Cleanup();
            return 0;
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
            _deviceManager.ConnectToCamera();
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
            _deviceManager.ConnectToCamera();
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

        private static void HandleInit(long id, JObject request)
        {
            EnsureDeviceManager();

            // Kamera-Erkennung kann nach ConnectToCamera() einen Moment dauern.
            // Bewusst NICHT blind SelectedCameraDevice nehmen (könnte ein
            // Platzhalter/Fremdgerät sein), sondern gezielt eine echte Kamera.
            var deadline = DateTime.UtcNow.AddSeconds(15);
            ICameraDevice camera = FindRealCamera();
            while (camera == null)
            {
                if (DateTime.UtcNow > deadline)
                {
                    ReplyError(id, "Keine Nikon-Kamera gefunden (USB/PTP prüfen)");
                    return;
                }
                Thread.Sleep(250);
                _deviceManager.ConnectToCamera();
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
            catch
            {
                // Fehler beim Transfer: capture-Kommando läuft in den Timeout.
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
    }
}
