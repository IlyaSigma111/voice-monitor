using System;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Windows.Forms;
using Newtonsoft.Json;

namespace VoiceMonitor
{
    public class SettingsForm : Form
    {
        private readonly string _modelDir;

        public AppSettings Settings { get; private set; }

        private TextBox _txtRecordingsPath;
        private TextBox _txtProfanity;
        private NumericUpDown _numPostSeconds;
        private Button _btnBrowse;
        private Button _btnDownloadModel;
        private Label _lblModelStatus;

        public SettingsForm(AppSettings settings, string modelDir)
        {
            Settings = new AppSettings
            {
                RecordingsDir = settings.RecordingsDir,
                ProfanityWords = settings.ProfanityWords.ToList(),
                PostRecordChunks = settings.PostRecordChunks
            };
            _modelDir = modelDir;

            InitializeForm();
        }

        private void InitializeForm()
        {
            this.Text = "Настройки";
            this.Size = new Size(520, 540);
            this.FormBorderStyle = FormBorderStyle.FixedDialog;
            this.MaximizeBox = false;
            this.MinimizeBox = false;
            this.StartPosition = FormStartPosition.CenterParent;
            this.BackColor = Color.FromArgb(30, 30, 46);
            this.ForeColor = Color.White;

            var padding = 20;
            var y = 20;
            var labelWidth = 160;
            var fieldX = labelWidth + 30;
            var fieldWidth = 300;

            // Папка записей
            var lbl1 = CreateLabel("Папка для записей:", new Point(padding, y), labelWidth);
            this.Controls.Add(lbl1);

            _txtRecordingsPath = new TextBox
            {
                Location = new Point(fieldX, y),
                Size = new Size(fieldWidth - 40, 28),
                Text = Settings.RecordingsDir,
                BackColor = Color.FromArgb(49, 50, 68),
                ForeColor = Color.White,
                BorderStyle = BorderStyle.FixedSingle,
                Font = new Font("Segoe UI", 9)
            };
            this.Controls.Add(_txtRecordingsPath);

            _btnBrowse = new Button
            {
                Text = "...",
                Location = new Point(fieldX + fieldWidth - 36, y),
                Size = new Size(32, 28),
                BackColor = Color.FromArgb(108, 92, 231),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Font = new Font("Segoe UI", 9, FontStyle.Bold),
                Cursor = Cursors.Hand
            };
            _btnBrowse.Click += (s, e) => BrowseFolder();
            this.Controls.Add(_btnBrowse);

            y += 50;

            // Запись после детекции (сек)
            var postSec = Settings.PostRecordChunks / 5;
            var lbl2 = CreateLabel("Запись после (сек):", new Point(padding, y), labelWidth);
            this.Controls.Add(lbl2);

            _numPostSeconds = new NumericUpDown
            {
                Location = new Point(fieldX, y),
                Size = new Size(80, 28),
                Minimum = 1,
                Maximum = 30,
                Value = postSec,
                BackColor = Color.FromArgb(49, 50, 68),
                ForeColor = Color.White,
                Font = new Font("Segoe UI", 9)
            };
            this.Controls.Add(_numPostSeconds);

            var lbl2note = CreateLabel("секунд после обнаружения", new Point(fieldX + 90, y + 4), 180);
            lbl2note.ForeColor = Color.FromArgb(160, 160, 176);
            this.Controls.Add(lbl2note);

            y += 50;

            // Список слов
            var lbl3 = CreateLabel("Слова для поиска:", new Point(padding, y), labelWidth);
            this.Controls.Add(lbl3);

            var lbl3note = CreateLabel("Каждое слово с новой строки", new Point(fieldX, y - 2), 180);
            lbl3note.ForeColor = Color.FromArgb(160, 160, 176);
            this.Controls.Add(lbl3note);

            y += 22;

            _txtProfanity = new TextBox
            {
                Location = new Point(fieldX, y),
                Size = new Size(fieldWidth, 200),
                Text = string.Join("\n", Settings.ProfanityWords),
                Multiline = true,
                ScrollBars = ScrollBars.Vertical,
                BackColor = Color.FromArgb(49, 50, 68),
                ForeColor = Color.White,
                BorderStyle = BorderStyle.FixedSingle,
                Font = new Font("Consolas", 9)
            };
            this.Controls.Add(_txtProfanity);

            y += 220;

            // Модель
            var lbl4 = CreateLabel("Модель:", new Point(padding, y), labelWidth);
            this.Controls.Add(lbl4);

            _lblModelStatus = CreateLabel("", new Point(fieldX, y + 4), 200);
            this.Controls.Add(_lblModelStatus);

            _btnDownloadModel = new Button
            {
                Text = "Скачать модель",
                Location = new Point(fieldX, y + 26),
                Size = new Size(140, 32),
                BackColor = Color.FromArgb(108, 92, 231),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Font = new Font("Segoe UI", 9, FontStyle.Bold),
                Cursor = Cursors.Hand
            };
            _btnDownloadModel.Click += (s, e) => DownloadModel();
            this.Controls.Add(_btnDownloadModel);

            UpdateModelStatus();

            y += 70;

            // Кнопки
            var btnSave = new Button
            {
                Text = "Сохранить",
                Location = new Point(220, y),
                Size = new Size(120, 36),
                BackColor = Color.FromArgb(40, 167, 69),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Font = new Font("Segoe UI", 10, FontStyle.Bold),
                Cursor = Cursors.Hand
            };
            btnSave.Click += (s, e) => SaveAndClose();
            this.Controls.Add(btnSave);

            var btnCancel = new Button
            {
                Text = "Отмена",
                Location = new Point(350, y),
                Size = new Size(120, 36),
                BackColor = Color.FromArgb(108, 92, 231),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Font = new Font("Segoe UI", 10, FontStyle.Bold),
                Cursor = Cursors.Hand
            };
            btnCancel.Click += (s, e) => this.DialogResult = DialogResult.Cancel;
            this.Controls.Add(btnCancel);
        }

        private Label CreateLabel(string text, Point location, int width)
        {
            return new Label
            {
                Text = text,
                Location = location,
                Size = new Size(width, 20),
                ForeColor = Color.FromArgb(162, 155, 254),
                Font = new Font("Segoe UI", 9, FontStyle.Bold)
            };
        }

        private void BrowseFolder()
        {
            using var dlg = new FolderBrowserDialog
            {
                Description = "Выберите папку для записей",
                UseDescriptionForTitle = true
            };
            if (dlg.ShowDialog() == DialogResult.OK)
            {
                _txtRecordingsPath.Text = dlg.SelectedPath;
            }
        }

        private void UpdateModelStatus()
        {
            if (Directory.Exists(_modelDir) && Directory.GetFiles(_modelDir, "*", SearchOption.AllDirectories).Length > 5)
            {
                _lblModelStatus.Text = "✓ Модель установлена";
                _lblModelStatus.ForeColor = Color.FromArgb(40, 167, 69);
                _btnDownloadModel.Enabled = false;
            }
            else
            {
                _lblModelStatus.Text = "✗ Модель не найдена";
                _lblModelStatus.ForeColor = Color.FromArgb(220, 53, 69);
                _btnDownloadModel.Enabled = true;
            }
        }

        private async void DownloadModel()
        {
            _btnDownloadModel.Enabled = false;
            _lblModelStatus.Text = "Скачивание...";
            _lblModelStatus.ForeColor = Color.FromArgb(255, 193, 7);

            var zipPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "model_temp.zip");
            var extractDir = _modelDir;

            try
            {
                using var client = new System.Net.Http.HttpClient { Timeout = TimeSpan.FromMinutes(10) };
                using var response = await client.GetAsync("https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip");
                response.EnsureSuccessStatusCode();

                var total = response.Content.Headers.ContentLength ?? 0;
                var downloaded = 0L;
                var buffer = new byte[81920];

                using var fs = new FileStream(zipPath, FileMode.Create, FileAccess.Write, FileShare.None);
                using var stream = await response.Content.ReadAsStreamAsync();

                while (true)
                {
                    var read = await stream.ReadAsync(buffer, 0, buffer.Length);
                    if (read == 0) break;
                    await fs.WriteAsync(buffer, 0, read);
                    downloaded += read;
                    if (total > 0)
                    {
                        var pct = (int)(downloaded * 100 / total);
                        this.Invoke(() => _lblModelStatus.Text = $"Скачивание: {pct}%");
                    }
                }

                this.Invoke(() => _lblModelStatus.Text = "Распаковка...");

                if (File.Exists(zipPath))
                {
                    System.IO.Compression.ZipFile.ExtractToDirectory(zipPath, extractDir, true);
                    File.Delete(zipPath);
                }

                var extractedDir = Directory.GetDirectories(extractDir).FirstOrDefault();
                if (extractedDir != null && extractedDir != extractDir)
                {
                    foreach (var dir in Directory.GetDirectories(extractedDir, "*", SearchOption.AllDirectories))
                    {
                        var target = dir.Replace(extractedDir, extractDir);
                        Directory.CreateDirectory(target);
                    }
                    foreach (var file in Directory.GetFiles(extractedDir, "*", SearchOption.AllDirectories))
                    {
                        var target = file.Replace(extractedDir, extractDir);
                        File.Move(file, target, true);
                    }
                    Directory.Delete(extractedDir, true);
                }

                UpdateModelStatus();
                _lblModelStatus.Text = "✓ Модель установлена";
                _lblModelStatus.ForeColor = Color.FromArgb(40, 167, 69);
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Ошибка: {ex.Message}", "Ошибка", MessageBoxButtons.OK, MessageBoxIcon.Error);
                _lblModelStatus.Text = "✗ Ошибка загрузки";
                _lblModelStatus.ForeColor = Color.FromArgb(220, 53, 69);
            }
            finally
            {
                _btnDownloadModel.Enabled = true;
            }
        }

        private void SaveAndClose()
        {
            Settings.RecordingsDir = _txtRecordingsPath.Text.Trim();
            Settings.ProfanityWords = _txtProfanity.Text.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries)
                .Select(w => w.Trim().ToLower())
                .Where(w => !string.IsNullOrEmpty(w))
                .ToList();
            Settings.PostRecordChunks = (int)_numPostSeconds.Value * 5;

            Directory.CreateDirectory(Settings.RecordingsDir);
            this.DialogResult = DialogResult.OK;
        }
    }
}
