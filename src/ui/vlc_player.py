"""Begrenzter, wiederverwendbarer Besitzer fuer native VLC-Ressourcen.

Das Modul kennt weder Tkinter noch OpenCV. Dadurch laesst sich der kritische
native Lebenszyklus mit einem kleinen VLC-Fake belastbar testen.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional


class PersistentVlcPlayer:
    """Haelt pro App-Lauf hoechstens ein aktives VLC-Player-Paar.

    Native ``stop``/``release``-Aufrufe duerfen den Aufrufer nicht blockieren.
    Ein defektes Paar wird deshalb atomar abgetrennt und von genau einem
    Hintergrund-Thread freigegeben. Solange dieser Thread laeuft, wird kein
    neues Paar erzeugt.
    """

    def __init__(
        self,
        vlc_module: Any,
        logger: Any,
        args: list[str],
        *,
        max_generations: int = 2,
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
    ) -> None:
        self._vlc = vlc_module
        self._logger = logger
        self._args = list(args)
        self._max_generations = max(1, int(max_generations))
        self._thread_factory = thread_factory

        self._lock = threading.RLock()
        self._instance: Any = None
        self._player: Any = None
        self._generation = 0
        self._creation_attempts = 0
        self._players_created = 0
        self._videos_started = 0
        self._preparing = False
        self._cleanup_pending = False
        self._cleanup_thread: Optional[threading.Thread] = None
        self._cleanup_result = "none"
        self._stranded_pair: Any = None
        self._closed = False
        self._disabled = False
        self._state = "new"

    def prepare(self) -> bool:
        """Erzeugt das eine VLC-Paar; fuer Warmup-Threads gedacht."""
        attempt = self._reserve_prepare()
        if attempt is None:
            with self._lock:
                return (
                    self._player is not None
                    and not self._disabled
                    and not self._closed
                )
        return self._run_prepare(attempt)

    def _reserve_prepare(self) -> Optional[int]:
        with self._lock:
            if (
                self._closed
                or self._disabled
                or self._cleanup_pending
                or self._preparing
                or self._creation_attempts >= self._max_generations
            ):
                return None
            if self._player is not None:
                return None
            self._preparing = True
            self._creation_attempts += 1
            attempt = self._creation_attempts
            self._state = "preparing"
            return attempt

    def _run_prepare(self, attempt: int) -> bool:
        instance = None
        player = None
        try:
            instance = self._vlc.Instance(self._args)
            player = instance.media_player_new()
            with self._lock:
                self._players_created += 1
        except Exception as exc:
            self._logger.warning(
                "VLC-LIFECYCLE prepare_failed generation=%s error=%s",
                attempt,
                exc,
            )
            if player is not None or instance is not None:
                # _preparing bleibt bis zur atomaren Cleanup-Reservierung wahr;
                # in diesem schmalen Fenster kann kein zweiter Aufbau starten.
                self._cleanup_detached(player, instance, "prepare_failed")
            with self._lock:
                self._preparing = False
                if self._creation_attempts >= self._max_generations:
                    self._disabled = True
                    self._state = "disabled"
                elif not self._cleanup_pending:
                    self._state = "prepare-error"
            return False

        publish = False
        with self._lock:
            self._preparing = False
            self._generation = attempt
            if not self._closed and not self._disabled and not self._cleanup_pending:
                self._instance = instance
                self._player = player
                self._state = "ready"
                publish = True

        if not publish:
            self._cleanup_detached(player, instance, "late_prepare_result")
            return False

        self._logger.info(
            "VLC-LIFECYCLE player_created generation=%s creations=%s",
            attempt,
            self._players_created,
        )
        return True

    def prepare_async(self) -> bool:
        """Startet einen kontrollierten Wiederaufbau, ohne den UI-Faden zu sperren."""
        next_generation = self._reserve_prepare()
        if next_generation is None:
            return False

        thread = self._thread_factory(
            target=lambda: self._run_prepare(next_generation),
            daemon=True,
            name=f"VLC-Prepare-{next_generation}",
        )
        try:
            thread.start()
        except Exception as exc:
            with self._lock:
                self._preparing = False
                self._disabled = True
                self._state = "disabled"
            self._logger.error(
                "VLC-LIFECYCLE prepare_thread_failed generation=%s error=%s",
                next_generation,
                exc,
            )
            return False
        return True

    def start(self, path: str, hwnd: int) -> bool:
        """Bindet ein Medium und startet es auf dem bereits vorbereiteten Player."""
        with self._lock:
            if (
                self._closed
                or self._disabled
                or self._cleanup_pending
                or self._preparing
                or self._player is None
                or self._instance is None
            ):
                return False
            player = self._player
            instance = self._instance
            generation = self._generation

        media = None
        setup_error = None
        media_release_ok = True
        try:
            media = instance.media_new(path)
            media.add_option("no-video-title-show")
            player.set_media(media)
        except Exception as exc:
            setup_error = exc
            self._logger.error(
                "VLC-LIFECYCLE set_media_failed generation=%s error=%s",
                generation,
                exc,
            )
        finally:
            if media is not None:
                try:
                    # libvlc_media_player_set_media behaelt eine eigene Referenz.
                    # Die von media_new() gelieferte Caller-Referenz gehoert uns.
                    media.release()
                except Exception as exc:
                    media_release_ok = False
                    self._logger.warning(
                        "VLC-LIFECYCLE media_release_failed generation=%s error=%s",
                        generation,
                        exc,
                    )

        if setup_error is not None or not media_release_ok:
            with self._lock:
                if not media_release_ok:
                    self._disabled = True
            reason = "media_release_failed" if not media_release_ok else "set_media_failed"
            self.retire_async(reason, expected_player=player)
            return False

        try:
            player.set_hwnd(hwnd)
            result = player.play()
            if result == -1:
                raise RuntimeError("play() returned -1")
        except Exception as exc:
            self._logger.error(
                "VLC-LIFECYCLE play_failed generation=%s error=%s",
                generation,
                exc,
            )
            self.retire_async("play_failed", expected_player=player)
            return False

        with self._lock:
            if player is not self._player:
                return False
            self._videos_started += 1
            self._state = "playing"
        return True

    def mark_ended(self) -> None:
        """Behaelt Player/Instanz am natuerlichen Clip-Ende fuer den naechsten Clip."""
        with self._lock:
            if self._player is not None and not self._cleanup_pending:
                self._state = "ready"

    def get_state(self) -> Any:
        """Liest den nativen Player-Zustand ohne interne Referenzen preiszugeben."""
        with self._lock:
            player = self._player
        if player is None:
            return None
        return player.get_state()

    def retire_async(self, reason: str, *, expected_player: Any = None) -> bool:
        """Trennt das aktive Paar ab und gibt es in maximal einem Thread frei."""
        with self._lock:
            if self._cleanup_pending:
                return False
            if expected_player is not None and expected_player is not self._player:
                return False

            player = self._player
            instance = self._instance
            self._player = None
            self._instance = None
            if player is None and instance is None:
                return False

            self._cleanup_pending = True
            self._cleanup_result = "running"
            self._state = "cleanup"
            generation = self._generation

        def release() -> None:
            cleanup_ok = True
            try:
                if player is not None:
                    try:
                        player.stop()
                    except Exception as exc:
                        cleanup_ok = False
                        self._logger.warning(
                            "VLC-LIFECYCLE stop_failed generation=%s error=%s",
                            generation,
                            exc,
                        )
                    try:
                        player.release()
                    except Exception as exc:
                        cleanup_ok = False
                        self._logger.warning(
                            "VLC-LIFECYCLE player_release_failed generation=%s error=%s",
                            generation,
                            exc,
                        )
                if instance is not None:
                    try:
                        instance.release()
                    except Exception as exc:
                        cleanup_ok = False
                        self._logger.warning(
                            "VLC-LIFECYCLE instance_release_failed generation=%s error=%s",
                            generation,
                            exc,
                        )
            finally:
                with self._lock:
                    self._cleanup_thread = None
                    if not cleanup_ok:
                        # Mindestens ein nativer Aufruf kam nicht bestaetigt
                        # zurueck. Das Paar bleibt als genau ein diagnostischer
                        # Rueckstand referenziert; VLC darf nie neu entstehen.
                        self._cleanup_pending = True
                        self._cleanup_result = "failed"
                        self._stranded_pair = (player, instance)
                        self._disabled = True
                        self._state = "disabled"
                    else:
                        self._cleanup_pending = False
                        self._cleanup_result = "succeeded"
                        self._stranded_pair = None
                        if self._closed:
                            self._state = "closed"
                        elif self._disabled or self._creation_attempts >= self._max_generations:
                            self._disabled = True
                            self._state = "disabled"
                        else:
                            self._state = "fallback"
                self._logger.info(
                    "VLC-LIFECYCLE cleanup_finished generation=%s reason=%s success=%s",
                    generation,
                    reason,
                    int(cleanup_ok),
                )

        thread = self._thread_factory(
            target=release,
            daemon=True,
            name=f"VLC-Cleanup-{generation}",
        )
        with self._lock:
            self._cleanup_thread = thread
        try:
            thread.start()
        except Exception as exc:
            with self._lock:
                self._cleanup_thread = None
                self._cleanup_pending = True
                self._cleanup_result = "failed"
                self._stranded_pair = (player, instance)
                self._disabled = True
                self._state = "disabled"
            self._logger.error(
                "VLC-LIFECYCLE cleanup_thread_failed generation=%s error=%s",
                generation,
                exc,
            )
            return False
        return True

    def _cleanup_detached(self, player: Any, instance: Any, reason: str) -> bool:
        """Fuehrt auch unvollstaendige oder verspaetete Erzeugungen begrenzt ab."""
        if player is None and instance is None:
            return False

        with self._lock:
            if self._cleanup_pending:
                # Dieser Fall ist nur bei einem verspaeteten, aufgegebenen
                # Prepare denkbar. Es wird bewusst kein zweiter Thread erzeugt;
                # der Prozess-Wachhund bleibt beim Shutdown das letzte Netz.
                self._logger.warning(
                    "VLC-LIFECYCLE detached_cleanup_skipped reason=%s", reason
                )
                return False
            self._player = player
            self._instance = instance
        return self.retire_async(reason, expected_player=player)

    def disable(self, reason: str) -> None:
        """Schaltet weitere VLC-Erzeugungen fuer diesen Prozess ab."""
        with self._lock:
            self._disabled = True
            if self._player is None and not self._cleanup_pending:
                self._state = "disabled"
        self._logger.warning("VLC-LIFECYCLE disabled reason=%s", reason)
        self.retire_async(reason)

    def close(self) -> None:
        """Nicht blockierender finaler Close-Hook fuer den App-Shutdown."""
        with self._lock:
            self._closed = True
            if self._player is None and not self._cleanup_pending:
                self._state = "closed"
        self.retire_async("app_shutdown")

    def snapshot(self) -> Dict[str, Any]:
        """Kleine, thread-sichere Diagnoseansicht ohne native VLC-Aufrufe."""
        with self._lock:
            return {
                "state": self._state,
                "generation": self._generation,
                "creations": self._players_created,
                "creation_attempts": self._creation_attempts,
                "videos": self._videos_started,
                "cleanup_pending": int(self._cleanup_pending),
                "cleanup_result": self._cleanup_result,
                "preparing": int(self._preparing),
                "disabled": self._disabled,
                "closed": self._closed,
                "has_player": self._player is not None,
            }
