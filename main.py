import os
import sys
import wave
import json
import logging
import threading
import time
import collections
import pystray
from PIL import Image, ImageDraw
from datetime import datetime
from pyaudio import PyAudio, paInt16
from vosk import Model, KaldiRecognizer

import config
from profanity_list import PROFANITY_WORDS
from profanity_detector import detect_profanity


class VoiceMonitor:
    def __init__(self):
        self.running = False
        self.model = None
        self.recognizer = None
        self.audio_buffer = collections.deque()
        self.buffer_lock = threading.Lock()
        self.is_recording = False
        self.record_buffer = collections.deque()
        self.record_lock = threading.Lock()
        self.post_record_chunks = 0
        self.pending_detection = None
        self.recordings_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), config.RECORDINGS_DIR)
        os.makedirs(self.recordings_dir, exist_ok=True)

        self._setup_logging()
        self._load_model()

    def _setup_logging(self):
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config.LOG_FILE)
        logging.basicConfig(
            filename=log_path,
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger(__name__)

    def _load_model(self):
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config.VOSK_MODEL_PATH)
        if not os.path.exists(model_path):
            self.logger.error(
                f"Модель Vosk не найдена по пути: {model_path}\n"
                f"Скачайте модель: https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip\n"
                f"Распакуйте в папку models/"
            )
            print(f"ОШИБКА: Модель не найдена: {model_path}")
            print("Скачайте: https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip")
            print("Распакуйте содержимое в: models/vosk-model-small-ru/")
            sys.exit(1)

        self.logger.info("Загрузка модели Vosk...")
        self.model = Model(model_path)
        self.recognizer = KaldiRecognizer(self.model, config.SAMPLE_RATE)
        self.recognizer.SetWords(True)
        self.logger.info("Модель загружена успешно")

    def _contains_profanity(self, text: str) -> tuple[bool, str]:
        is_prof, found = detect_profanity(text)
        if is_prof:
            return True, found
        text_lower = text.lower()
        for word in PROFANITY_WORDS:
            if word in text_lower:
                return True, word
        return False, ""

    def _save_recording(self, audio_data: bytes, profane_text: str):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"detect_{timestamp}.wav"
        filepath = os.path.join(self.recordings_dir, filename)

        try:
            with wave.open(filepath, "wb") as wf:
                wf.setnchannels(config.CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(config.SAMPLE_RATE)
                wf.writeframes(audio_data)

            log_entry = os.path.join(self.recordings_dir, f"detections_{datetime.now().strftime('%Y-%m')}.log")
            with open(log_entry, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} | {filename} | Текст: {profane_text}\n")

            self.logger.info(f"Сохранено: {filename} | Текст: {profane_text}")
        except Exception as e:
            self.logger.error(f"Ошибка сохранения: {e}")

    def _get_total_audio_data(self):
        with self.buffer_lock:
            all_audio = b"".join(self.audio_buffer)
        return all_audio

    def _get_record_data(self):
        with self.record_lock:
            all_audio = b"".join(self.record_buffer)
        return all_audio

    def _add_to_buffer(self, data: bytes):
        with self.buffer_lock:
            self.audio_buffer.append(data)
            max_bytes = config.SAMPLE_RATE * config.BUFFER_SECONDS * 2
            while len(self.audio_buffer) > 0 and sum(len(x) for x in self.audio_buffer) > max_bytes:
                self.audio_buffer.popleft()

    def _add_to_record_buffer(self, data: bytes):
        with self.record_lock:
            self.record_buffer.append(data)
            max_bytes = config.SAMPLE_RATE * (config.BUFFER_SECONDS + config.POST_RECORD_SECONDS) * 2
            while len(self.record_buffer) > 0 and sum(len(x) for x in self.record_buffer) > max_bytes:
                self.record_buffer.popleft()

    def _create_tray_icon(self):
        img = Image.new("RGB", (64, 64), color=(70, 70, 70))
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 54, 54], outline="red", width=3)
        draw.line([(20, 20), (44, 44)], fill="red", width=3)
        draw.line([(44, 20), (20, 44)], fill="red", width=3)
        return img

    def _on_tray_click(self, tray, item):
        if str(item) == "Выход":
            self.running = False
            tray.stop()
        elif str(item) == "Папка записей":
            os.startfile(self.recordings_dir)

    def _start_monitoring(self):
        pa = PyAudio()
        chunk_size = int(config.SAMPLE_RATE * config.CHUNK_DURATION)

        try:
            stream = pa.open(
                format=paInt16,
                channels=config.CHANNELS,
                rate=config.SAMPLE_RATE,
                input=True,
                frames_per_buffer=chunk_size,
            )
        except Exception as e:
            self.logger.error(f"Ошибка открытия аудио потока: {e}")
            print(f"Ошибка: {e}")
            return

        self.logger.info("Начало мониторинга...")
        self.running = True
        self.audio_buffer.clear()
        self.record_buffer.clear()
        self.is_recording = False
        self.post_record_chunks = 0
        self.pending_detection = None
        max_post_chunks = int(config.POST_RECORD_SECONDS / config.CHUNK_DURATION)

        try:
            while self.running:
                try:
                    data = stream.read(chunk_size, exception_on_overflow=False)
                except Exception as e:
                    self.logger.error(f"Ошибка чтения аудио: {e}")
                    continue

                self._add_to_buffer(data)
                self._add_to_record_buffer(data)

                if self.is_recording:
                    self.post_record_chunks += 1
                    if self.post_record_chunks >= max_post_chunks:
                        audio_data = self._get_record_data()
                        if audio_data and self.pending_detection:
                            text, found_words = self.pending_detection
                            self._save_recording(audio_data, f"{text} [{found_words}]")
                        self.record_buffer.clear()
                        self.is_recording = False
                        self.post_record_chunks = 0
                        self.pending_detection = None
                    continue

                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    text = result.get("text", "")

                    if text:
                        is_prof, found = self._contains_profanity(text)
                        if is_prof:
                            self.is_recording = True
                            self.post_record_chunks = 0
                            self.pending_detection = (text, found)
                else:
                    partial = json.loads(self.recognizer.PartialResult())
                    partial_text = partial.get("partial", "")
                    if partial_text:
                        is_prof, found = self._contains_profanity(partial_text)
                        if is_prof:
                            self.is_recording = True
                            self.post_record_chunks = 0
                            self.pending_detection = (partial_text, found)

        except KeyboardInterrupt:
            self.logger.info("Остановка по Ctrl+C")
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()
            self.logger.info("Мониторинг остановлен")

    def run(self):
        icon = pystray.Icon(
            "voice_monitor",
            self._create_tray_icon(),
            "Voice Monitor",
            menu=pystray.Menu(
                pystray.MenuItem("Папка записей", self._on_tray_click),
                pystray.MenuItem("Выход", self._on_tray_click),
            ),
        )

        monitor_thread = threading.Thread(target=self._start_monitoring, daemon=True)
        monitor_thread.start()

        icon.run()


if __name__ == "__main__":
    monitor = VoiceMonitor()
    monitor.run()
