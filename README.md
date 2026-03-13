# Grace AI Bot (Discord)

Bot Discord sederhana bernama **Grace**.

Fitur:

- Menjawab saat dipanggil dengan format yang jelas, misalnya `Grace, bantu saya`, `Grace. bantu saya`, atau mention bot.
- Pesan yang hanya berisi `Grace` tidak akan memicu bot.
- Saat ditanya siapa dirinya, bot akan memperkenalkan diri:
  - `Saya adalah Grace, asisten AI DPNP yang dibuat oleh Brann. Saya siap membantu menjawab pertanyaan dan memberikan penjelasan dengan jelas.`
- Mengetahui tanggal, jam, dan periode waktu saat ini secara real-time, termasuk konteks seperti dini hari, pagi, siang, sore, atau malam.
- Menyimpan riwayat percakapan terbaru per user secara persisten agar jawaban lanjutan tetap nyambung.
- Membaca beberapa pesan sebelumnya di channel sebagai konteks tambahan sebelum menjawab.
- Menjawab pertanyaan user dengan AI (Gemini API).
- Membaca cuaca real-time berdasarkan lokasi yang diminta user.
- Mengambil berita populer terbaru secara real-time dari feed berita.
- Siap memakai PostgreSQL Railway melalui `DATABASE_URL` agar history tetap aman saat redeploy.
- Dapat membaca dan menganalisis gambar yang diunggah user (attachment image) menggunakan Gemini Vision.
- Bisa mengambil gambar dari pesan yang sedang di-reply (reply message) untuk dianalisis.
- Mendukung mode OCR (ekstrak teks dari gambar) dan mode ringkasan visual terstruktur.

## 1) Setup

1. Masuk ke folder project:
   - `cd grace-ai-bot`
2. Buat virtual environment (opsional tapi disarankan):
   - `python -m venv .venv`
   - Windows PowerShell: `.venv\\Scripts\\Activate.ps1`
3. Install dependency:
   - `pip install -r requirements.txt`
4. Copy `.env.example` jadi `.env`, lalu isi token:
   - `DISCORD_TOKEN`
   - `GEMINI_API_KEY`
   - Opsional: `BOT_TIMEZONE` untuk zona waktu bot, default `Asia/Jakarta`

## 2) Jalankan

- `python -m src.bot`

## 2.1) Deploy ke Railway

1. Push project `grace-ai-bot` ke GitHub.
2. Buka Railway lalu buat project baru dari repository GitHub tersebut.
3. Pastikan root directory mengarah ke folder `grace-ai-bot` jika repository berisi lebih dari satu project.
4. Railway akan install dependency dari `requirements.txt` dan menjalankan process dari `Procfile`:
   - `worker: python -m src.bot`
5. Tambahkan environment variables berikut di Railway:
   - `DISCORD_TOKEN`
   - `GEMINI_API_KEY`
   - `DATABASE_URL` (disarankan, dari Railway PostgreSQL agar history persisten)
   - `BOT_NAME=Grace`
   - `BOT_TIMEZONE=Asia/Jakarta` (opsional)
   - `GLOBAL_RPM_LIMIT=4` (opsional)
   - `USER_COOLDOWN_SEC=8` (opsional)
   - `HISTORY_MAX_TURNS=6` (opsional, jumlah pasangan tanya-jawab yang disimpan per user)
   - `CHANNEL_HISTORY_MESSAGES=6` (opsional, jumlah pesan sebelumnya di channel yang dibaca sebagai konteks)
   - `WEATHER_DEFAULT_LOCATION=Jakarta` (opsional, dipakai jika user tidak menyebut lokasi)
   - `NEWS_MAX_ITEMS=5` (opsional, jumlah headline berita populer yang dikirim)
   - `NEWS_REGION_LANGUAGE=id` (opsional, bahasa feed berita)
   - `NEWS_REGION_COUNTRY=ID` (opsional, region feed berita)
   - `HISTORY_BACKEND=auto` (opsional, `auto` akan memakai PostgreSQL jika `DATABASE_URL` tersedia)
   - `MAX_IMAGE_BYTES=8388608` (opsional, default 8MB per gambar)
   - `MAX_IMAGES_PER_REQUEST=3` (opsional, default maksimal 3 gambar per request)
6. Deploy service, lalu cek tab logs sampai muncul pesan login bot Discord.

Catatan:

- Jangan upload file `.env` ke repository.
- Bot Discord seperti ini lebih cocok dijalankan sebagai `worker`, bukan aplikasi web.
- Untuk deployment Railway yang stabil, tambahkan plugin PostgreSQL dan map `DATABASE_URL` ke service bot.
- Jika repository Anda private, hubungkan akun GitHub ke Railway lebih dulu.

## 3) Cara pakai

- Mention bot, atau ketik pesan yang diawali nama bot lalu tanda baca.
- Contoh:
  - `Grace, apa itu machine learning?`
  - `Grace. siapa kamu?`
  - `Grace, sekarang jam berapa?`
  - `Grace, sekarang tanggal berapa?`
- `Grace, cuaca di Bandung sekarang bagaimana?`
- `Grace, cuaca sekarang` (akan memakai lokasi default)
- `Grace, berita populer hari ini`
- `Grace, headline terbaru`
- `Grace, berita teknologi`
- `Grace, berita tentang AI`
- `Grace, hapus history`
  - `@Grace tolong jelaskan Python`
  - `Grace, tolong jelaskan gambar ini` sambil upload gambar
  - `@Grace apa yang kamu lihat di gambar ini?` sambil upload gambar
  - Reply ke pesan yang berisi gambar: `Grace, jelaskan gambar ini`
  - OCR: `Grace, OCR gambar ini` atau `Grace, baca teks pada gambar ini`
  - Ringkasan visual: `Grace, ringkas visual gambar ini dengan format poin`

Catatan fitur gambar:

- Gambar diproses dari file attachment Discord (png/jpg/jpeg/webp/gif/bmp/heic/heif).
- Grace juga bisa membaca gambar dari pesan yang Anda reply, bukan hanya attachment di pesan saat ini.
- Jika pesan hanya berisi gambar tanpa teks, Grace akan tetap menganalisis gambar dengan instruksi default.
- Jika ukuran gambar melebihi batas, Grace akan mengirim peringatan via DM.

Catatan history dan data real-time:

- Riwayat percakapan akan memakai PostgreSQL jika `DATABASE_URL` tersedia. Jika tidak, bot akan fallback ke `data/conversation_history.json`.
- Grace juga membaca beberapa pesan sebelumnya di channel agar bisa mengikuti percakapan yang sedang berlangsung.
- Data cuaca menggunakan Open-Meteo (geocoding + forecast) tanpa API key tambahan.
- Data berita populer diambil dari feed Google News RSS sesuai region yang dikonfigurasi, dan bisa difilter berdasarkan topik.

Rekomendasi Railway:

- Gunakan service `worker`, bukan web service.
- Tambahkan Railway PostgreSQL agar history percakapan tidak hilang saat restart atau redeploy.
- Setelah deploy, cek log startup. Grace akan menampilkan backend history aktif, misalnya `history_backend=postgres`.

## 4) Dapatkan Gemini API Key

1. Buka Google AI Studio dan buat API key.
2. Masukkan key tersebut ke `GEMINI_API_KEY` pada file `.env`.
