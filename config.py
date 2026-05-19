# Конфигурация приложения

# Путь к папке для сохранения записей
RECORDINGS_DIR = "recordings"

# Параметры аудио
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 0.2  # секунд на один чанк для распознавания
BUFFER_SECONDS = 5    # сколько секунд хранить в буфере до детекции
POST_RECORD_SECONDS = 3  # сколько секунд записывать после детекции мата

# Настройки Vosk
VOSK_MODEL_PATH = "models/vosk-model-small-ru"

# Логирование
LOG_FILE = "monitor.log"
