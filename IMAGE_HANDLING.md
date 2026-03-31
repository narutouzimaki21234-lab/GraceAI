# 🖼️ Grace Bot - Image Handling Guide

Bot Grace sekarang dilengkapi dengan kemampuan **analisis gambar berbasis AI** menggunakan Google Gemini API!

## ✨ Fitur Image Handling

### 1. **Analisis Gambar Otomatis**
Kirim gambar atau JPG ke bot, dan Grace akan menganalisisnya secara otomatis:

```
Anda: [mengirim gambar]
Grace: Analisis detail lengkap tentang gambar
```

### 2. **Mode-Mode Analisis**

#### Mode Normal (Default)
Cukup kirim gambar, bot akan memberikan deskripsi lengkap:
```
Grace, [kirim gambar]
→ Bot memberikan deskripsi umum gambar
```

#### Mode OCR (Baca Teks)
Ekstrak semua teks dari gambar:
```
Grace, ocr [kirim gambar]
Grace, baca teks [kirim gambar]
→ Bot menyalin seluruh teks yang terlihat di gambar
```

#### Mode Ringkasan Visual
Ringkas gambar dalam format poin:
```
Grace, ringkas visual [kirim gambar]
Grace, format poin [kirim gambar]
→ Bot memberikan ringkasan dalam poin-poin terstruktur
```

### 3. **Multiple Images**
Kirim hingga 3 gambar sekaligus:
```
Grace, analisis gambar-gambar ini [3 attachments]
→ Bot menganalisis semua gambar
```

### 4. **Reply dengan Gambar**
Balas pesan yang berisi gambar:
```
[Pesan sebelumnya dengan gambar]
→ Grace, apa ini?
→ Bot menganalisis gambar dari balasan
```

## ⚙️ Konfigurasi

Semua setting image handling dapat dikustomisasi di `.env`:

```env
# Ukuran maksimal per gambar (bytes)
MAX_IMAGE_BYTES=8388608  # 8 MB

# Jumlah maksimal gambar per request
MAX_IMAGES_PER_REQUEST=3

# Format Gemini model untuk vision
GEMINI_MODEL=gemini-2.5-flash
```

## 📋 Format File yang Didukung

✅ Supported:
- PNG (.png)
- JPEG (.jpg, .jpeg)
- WebP (.webp)
- GIF (.gif)
- HEIC/HEIF (.heic, .heif)
- BMP (.bmp)

❌ Not supported:
- Dokumen PDF
- Vektor (SVG)
- Raw format

## ⚡ Contoh Penggunaan

### Contoh 1: Analisis Foto Biasa
```
Anda: Grace, apa yang ada di gambar ini? [foto.jpg]
Grace: Saya melihat sebuah pemandangan alam dengan... [detail lengkap]
```

### Contoh 2: Extract Teks dari Screenshot
```
Anda: Grace, salin teksnya ocr [screenshot.png]
Grace: [copy seluruh teks dari screenshot]
```

### Contoh 3: Analisis Dokumen Scan
```
Anda: Grace, ringkas visual dokumen ini [scan.jpg]
Grace: 
- Judul: ...
- Poin Utama: ...
- Kesimpulan: ...
```

## 🔒 Batasan & Catatan

1. **Ukuran File**: Maks 8 MB per gambar
2. **Jumlah Gambar**: Maks 3 gambar per request
3. **Rate Limiting**: 
   - User cooldown: 8 detik antar request
   - Global limit: 4 request per menit
4. **API Key**: Pastikan `GEMINI_API_KEY` sudah diset di `.env`
5. **Privacy**: Gambar dikirim ke Google Gemini API untuk dianalisis

## 🛠️ Troubleshooting

### Gambar tidak dianalisis
```
✓ Cek: API key sudah benar di .env
✓ Cek: Format file support (PNG, JPG, WebP, dll)
✓ Cek: Ukuran file < 8 MB
```

### "Limit Gemini API sedang tercapai"
```
✓ Tunggu beberapa detik
✓ Coba lagi dengan image yang lebih sederhana
✓ Cek quota API di Google AI Studio
```

### "Ukuran gambar terlalu besar"
```
✓ Compress gambar sebelum upload
✓ Tools: TinyPNG, ImageOptim, atau kompres manual
```

## 📞 Support

Jika ada masalah:
1. Cek `.env` sudah benar
2. Lihat error message di console bot
3. Coba dengan test image yang berbeda

---

**Bot Grace v2.0** - Dengan kekuatan Gemini AI 🚀
