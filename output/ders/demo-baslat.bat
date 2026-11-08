@echo off
cd /d "%~dp0..\.."
if not exist ".venv\Scripts\python.exe" (
  echo Sanal ortam yok. 01-hizli-calistirma.md dosyasindaki kurulumu uygulayin.
  pause
  exit /b 1
)
echo Tarayicida http://127.0.0.1:8501 adresini acin.
echo Sunucu zaten aciksa bu pencereyi kapatabilirsiniz.
".venv\Scripts\python.exe" -m streamlit run src/sentinel_crop_pipeline/dashboard/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
pause
