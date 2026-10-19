@echo off
cd /d "C:\Users\asus\Documents\FICC Proj"
echo Starting FX Structuring Engine in Docker...
docker run -p 8504:8501 fx-structuring-engine
pause