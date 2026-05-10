@echo off
chcp 65001 >nul
echo KDCA 주간 카카오톡 발송 예약 작업 등록 중...

schtasks /create ^
  /tn "KDCA Weekly Kakao Report" ^
  /tr "\"C:\Users\Administrator\AppData\Local\Python\pythoncore-3.14-64\python.exe\" \"D:\감영병 모니터링\kdca_kakao_report.py\"" ^
  /sc WEEKLY ^
  /d FRI ^
  /st 08:30 ^
  /f

if %errorlevel% equ 0 (
    echo.
    echo 성공: 매주 금요일 오전 8:30에 카카오톡으로 자동 발송됩니다.
    schtasks /query /tn "KDCA Weekly Kakao Report" /fo LIST
) else (
    echo.
    echo 오류: 관리자 권한으로 실행해주세요.
    echo 이 파일을 마우스 오른쪽 클릭 후 '관리자 권한으로 실행' 선택
)

pause
