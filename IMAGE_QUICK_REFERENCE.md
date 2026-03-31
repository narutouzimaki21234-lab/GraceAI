# 📸 Image Handling - Quick Reference

## Fitur & Command Cepat

### ✨ Buat Bot Paham Gambar

Bot Grace sudah bisa analyze gambar! Cukup kirim gambar, dia akan respond:

```
Kirim gambar → Grace analyze & reply ✅
```

### 🎯 Command Mode

| Command | Hasil |
|---------|-------|
| `Grace, [kirim gambar]` | Analisis deskriptif |
| `Grace, ocr [gambar]` | Extract semua teks |
| `Grace, baca teks [gambar]` | Same as OCR |
| `Grace, ringkas visual [gambar]` | Ringkasan format poin |
| `Grace, [kirim 3 gambar]` | Analisis multiple images |

### 🔧 Config (.env)

```env
GEMINI_API_KEY=AIza...    # Required untuk image analysis
GEMINI_MODEL=gemini-2.5-flash  # Latest model dengan vision
MAX_IMAGE_BYTES=8388608   # 8 MB per image
MAX_IMAGES_PER_REQUEST=3  # Hingga 3 image per request
```

### ✅ Status Fitur

- ✅ Text Analysis Gambar
- ✅ Multiple Images (hingga 3)
- ✅ OCR Mode
- ✅ Summary Mode
- ✅ Auto-detection Image
- ✅ Compression Support
- ✅ Error Handling

### ⚡ Supported Formats

PNG, JPG, JPEG, WebP, GIF, BMP, HEIC, HEIF

### 📊 Rate Limits

- Per user: 8 detik cooldown
- Global: 4 requests/minute

---

**Ready to go!** 🚀 Bot siap terima & analyze gambar!
