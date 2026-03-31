# ✅ Grace Bot Image Handling - Setup Verification

## 📋 Status Implementasi Image Feature

### ✨ Features yang Sudah Aktif

| Feature | Status | Lokasi Kode |
|---------|--------|------------|
| 🖼️ Extract Images dari Attachment | ✅ Aktif | `_extract_images()` di bot.py |
| 🤖 Gemini Vision API Integration | ✅ Aktif | `ask_ai_with_images()` di bot.py |
| 📸 Multiple Image Support | ✅ Aktif | MAX_IMAGES_PER_REQUEST = 3 |
| 🔍 OCR Mode | ✅ Aktif | `_detect_vision_mode()` di bot.py |
| 📝 Summary/Ringkasan Mode | ✅ Aktif | Vision mode detection |
| 📐 Image Size Validation | ✅ Aktif | MAX_IMAGE_BYTES = 8388608 |
| 🔗 Reply Message Image Support | ✅ Aktif | `message.reference.resolved` |
| ⚡ Auto-detection & Routing | ✅ Aktif | `on_message()` handler |
| 🛡️ Error Handling | ✅ Aktif | Comprehensive try-catch |

---

## 🔧 Konfigurasi Saat Ini

### `.env` Settings

```env
# API Configuration
DISCORD_TOKEN=MTQ4MTc4ODUyNzI2MjgzMDczNA.Gjxmy6...
GEMINI_API_KEY=AIzaSyC4d8uGVEH3_4SbjTRlEQLtRKiRp_LK_Ks
GEMINI_MODEL=gemini-2.5-flash
BOT_NAME=Grace

# Image Handling
MAX_IMAGE_BYTES=8388608        # 8 MB per image
MAX_IMAGES_PER_REQUEST=3       # Up to 3 images

# Conversation & Context
HISTORY_MAX_TURNS=6
CHANNEL_HISTORY_MESSAGES=6

# Rate Limiting
GLOBAL_RPM_LIMIT=4
USER_COOLDOWN_SEC=8

# Timezone & Locale
BOT_TIMEZONE=Asia/Jakarta

# Features
WEATHER_DEFAULT_LOCATION=Jakarta
NEWS_MAX_ITEMS=5
NEWS_REGION_LANGUAGE=id
NEWS_REGION_COUNTRY=ID
```

---

## 📝 Alur Kerja Image Processing

```
1. User kirim pesan + attachment (gambar)
   ↓
2. on_message() handler trigger
   ↓
3. _extract_images() → validasi & download gambar
   ↓
4. Check ukuran, format, jumlah file
   ↓
5. IF images found:
   - ask_ai_with_images() call
   - Gemini API process gambar
   - Return analisis text
   ↓
6. ELSE:
   - ask_ai() untuk text normal
   ↓
7. Reply ke user dengan hasil
   ↓
8. _store_conversation_turn() simpan history
```

---

## 🚀 Cara Menggunakan

### Scenario 1: Analisis Foto Biasa
```
User: Grace, apa ini? [foto.jpg]
Bot:  [analisis detail gambar]
```

### Scenario 2: Extract Teks (OCR)
```
User: Grace, ocr gambar ini [screenshot.png]
Bot:  [salin semua teks dari screenshot]
```

### Scenario 3: Ringkasan Visual
```
User: Grace, ringkas visual [dokumen.jpg]
Bot:  [ringkasan dalam format poin]
```

### Scenario 4: Multiple Images
```
User: Grace, bandingkan 3 gambar [img1.jpg] [img2.jpg] [img3.jpg]
Bot:  [analisis perbandingan 3 gambar]
```

### Scenario 5: Reply dengan Gambar
```
[Pesan sebelumnya: attachment.jpg]
User: Grace, apa itu?
Bot:  [analisis gambar dari pesan sebelumnya]
```

---

## ✅ Pre-requisites Checklist

- [x] `discord.py` version 2.6.0+ installed
- [x] `google-generativeai` installed (vision support)
- [x] `python-dotenv` installed (load .env)
- [x] `DISCORD_TOKEN` set at .env
- [x] `GEMINI_API_KEY` set at .env (starts with "AIza")
- [x] `GEMINI_MODEL` set to gemini-2.5-flash (supports vision)
- [x] MAX_IMAGE_BYTES configured (default 8MB)
- [x] MAX_IMAGES_PER_REQUEST configured (default 3)

---

## 🔍 Testing Image Features Locally

### Test 1: Basic Image Analysis
```python
# Buka DM dengan bot
Message: "Grace, jelaskan gambar ini [test.jpg]"
Expected: Bot analyze & reply dengan deskripsi
```

### Test 2: Multiple Images
```python
# Kirim 3 gambar sekaligus
Message: "Grace, apa persamaannya [1.jpg] [2.jpg] [3.jpg]"
Expected: Bot analyze & compare
```

### Test 3: OCR Mode
```python
# Screenshot atau gambar dengan teks
Message: "Grace, ocr [screenshot.jpg]"
Expected: Bot copy semua teks
```

### Test 4: Error Handling
```python
# Gambar > 8MB
Message: "Grace, [large_image.jpg]"
Expected: Error message "Ukuran gambar terlalu besar"
```

---

## 🛠️ Dependencies

**Wajib untuk image handling:**
```
discord.py==2.6.0
python-dotenv==1.1.1
google-generativeai                # ⭐ Image support
psycopg[binary]==3.2.6            # Optional: PostgreSQL history
```

**Installation:**
```bash
pip install -r requirements.txt
```

---

## 🚨 Troubleshooting

### ❌ "GEMINI_API_KEY tidak valid"
```
✓ Cek ApiKey dimulai dengan "AIza"
✓ Buka Google AI Studio: https://aistudio.google.com/app/apikey
✓ Generate key baru jika perlu
✓ Update di .env
✓ Restart bot
```

### ❌ "Ukuran gambar terlalu besar"
```
✓ MAX_IMAGE_BYTES = 8388608 (8 MB)
✓ Compress image terlebih dahulu
✓ Atau ubah MAX_IMAGE_BYTES di .env
```

### ❌ "Limit Gemini API sedang tercapai"
```
✓ Rate limiting tercapai (4 req/min global)
✓ Tunggu beberapa saat
✓ Atau cek quota di Google AI Studio
```

### ❌ "Jenis gambar tidak support"
```
Supported formats: PNG, JPG, JPEG, WebP, GIF, BMP, HEIC, HEIF
❌ Not supported: PDF, SVG, WebM, MP4, dll
```

---

## 📊 Monitoring

**Log messages untuk image processing:**

```
[Image processing start]
"Gagal membaca file gambar: ..."
"Ukuran gambar terlalu besar: ..."
"Limit Gemini API tercapai"
"Analisis gambar dibatasi oleh safety"

[Success]
"[dengan gambar]" akan terlihat di history
```

---

## 🎯 Environment Variables Summary

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| DISCORD_TOKEN | ✅ | - | Bot token dari Discord Developer |
| GEMINI_API_KEY | ✅ | - | API key dari Google AI Studio |
| GEMINI_MODEL | ❌ | gemini-2.5-flash | Model dengan vision capability |
| BOT_NAME | ❌ | Grace | Nama bot di Discord |
| MAX_IMAGE_BYTES | ❌ | 8388608 | Max 8 MB per image |
| MAX_IMAGES_PER_REQUEST | ❌ | 3 | Max 3 images per request |

---

## 📞 Support & Resources

- **Discord.py Docs**: https://discordpy.readthedocs.io/
- **Google Gemini API**: https://ai.google.dev/
- **Image Handling Guide**: [IMAGE_HANDLING.md](IMAGE_HANDLING.md)
- **Quick Reference**: [IMAGE_QUICK_REFERENCE.md](IMAGE_QUICK_REFERENCE.md)

---

**✨ Bot Grace siap menerima dan analyze gambar!** 🚀

Last Updated: March 31, 2026
