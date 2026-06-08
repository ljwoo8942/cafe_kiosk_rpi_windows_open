# Cafe Kiosk RPi Windows Open

음성 인식과 음성 안내를 중심으로 만든 접근성 지향 카페 키오스크입니다. 일반 터치 키오스크 사용이 어려운 노약자분들도 메뉴, 옵션, 주문 확인, 결제 진행을 음성 안내에 따라 차근차근 진행할 수 있도록 설계했습니다.

터치 주문도 함께 지원하지만, 핵심 목표는 사용자가 메뉴와 옵션을 말하면 프로그램이 부족한 정보를 다시 질문하고 주문을 완성해 주는 대화형 음성 주문 흐름입니다.

## 지원 환경

- Windows 10 / 11
- Raspberry Pi OS / Linux
- Python 3.13.12 기준으로 개발 및 테스트
- Raspberry Pi 5인치 / 7인치 터치 디스플레이 구성 지원

Raspberry Pi에서는 `xrandr`로 연결된 모니터 크기와 위치를 감지해 작은 화면은 음성+터치 주문 창, 큰 화면은 키오스크 주문 창으로 자동 배치합니다. 단일 소형 화면에서는 탭 기반 풀스크린 UI로 실행됩니다.

## 다운로드

최신 설치 파일은 GitHub Releases에서 받을 수 있습니다. 일반 사용자는 아래 파일만 다운로드하면 됩니다.

- Windows: [CafeKiosk-Windows-Setup-1.3.0.exe](https://github.com/ljwoo8942/cafe_kiosk_rpi_windows_open/releases/download/v1.3.0/CafeKiosk-Windows-Setup-1.3.0.exe)
- Raspberry Pi 더블클릭 설치: [CafeKiosk-RPi-Installer-1.3.0.zip](https://github.com/ljwoo8942/cafe_kiosk_rpi_windows_open/releases/download/v1.3.0/CafeKiosk-RPi-Installer-1.3.0.zip)
- Raspberry Pi 직접 설치: [cafe-kiosk-rpi_1.3.0_all.deb](https://github.com/ljwoo8942/cafe_kiosk_rpi_windows_open/releases/download/v1.3.0/cafe-kiosk-rpi_1.3.0_all.deb)
- Windows 무설치 압축본: [CafeKiosk-Windows-Portable-1.3.0.zip](https://github.com/ljwoo8942/cafe_kiosk_rpi_windows_open/releases/download/v1.3.0/CafeKiosk-Windows-Portable-1.3.0.zip)

릴리즈 페이지:
[Cafe Kiosk v1.3.0](https://github.com/ljwoo8942/cafe_kiosk_rpi_windows_open/releases/tag/v1.3.0)

## 설치 방법

Windows:

1. `CafeKiosk-Windows-Setup-1.3.0.exe`를 다운로드합니다.
2. 설치 파일을 실행합니다.
3. 설치가 끝나면 바탕화면의 `BEAN & BREW Cafe Kiosk` 바로가기로 실행합니다.

설치 중 인터넷 연결이 필요할 수 있습니다. Python 3.13 또는 필요한 Python 패키지가 없는 경우 설치 파일이 자동으로 설치를 시도합니다.

Windows에서 SmartScreen 경고가 표시될 수 있습니다. 개인 개발자가 배포한 서명되지 않은 설치 파일에서 발생할 수 있으며, 실행하려면 `추가 정보`를 누른 뒤 `실행`을 선택합니다.

Windows 삭제:

1. Windows 설정의 앱 목록에서 `BEAN & BREW Cafe Kiosk`를 제거합니다.
2. 제거 시 설치 폴더, 가상환경, TTS 캐시, Dialogflow 인증 파일, 사용자 설정, 주문 이력 DB, 로그, 업데이트 임시 파일까지 함께 삭제됩니다.
3. Windows 무설치 압축본을 사용한 경우에는 압축을 푼 폴더에서 `powershell -ExecutionPolicy Bypass -File .\uninstall_windows.ps1 -RemoveAppRoot`를 실행하면 앱 폴더와 사용자 데이터까지 함께 정리됩니다.

Raspberry Pi / Linux 더블클릭 설치:

1. `CafeKiosk-RPi-Installer-1.3.0.zip`을 다운로드합니다.
2. 압축을 풉니다.
3. `설치하기.desktop` 파일을 더블클릭합니다.
4. 실행 허용 또는 신뢰 확인 창이 뜨면 허용합니다.
5. 설치 창에서 `설치 시작` 버튼을 누릅니다.
6. 권한 확인 창이 뜨면 Raspberry Pi 비밀번호를 입력합니다.
7. 설치가 끝나면 `프로그램 실행` 버튼을 누릅니다.

설치 창이 열리지 않는 경우 같은 폴더의 `설치안내.txt`를 확인하거나 터미널에서 `bash install_rpi_gui.sh`를 실행합니다. 그래도 실패하면 아래 직접 설치 방법을 사용합니다.

Raspberry Pi / Linux 직접 설치:

1. `cafe-kiosk-rpi_1.3.0_all.deb`를 다운로드합니다.
2. 파일이 있는 폴더에서 아래 명령을 실행합니다.

```bash
sudo apt install ./cafe-kiosk-rpi_1.3.0_all.deb
cafe-kiosk
```

설치 중 인터넷 연결이 필요할 수 있습니다. Python 패키지, TTS, 마이크 관련 구성요소를 설치하기 때문입니다.

Raspberry Pi / Linux 삭제:

```bash
sudo apt remove cafe-kiosk-rpi
```

패키지 설치 파일, `/opt/cafe-kiosk`의 가상환경, 설치 로그(`install_logs`, `installer_logs`, `logs`), 런처, TTS 캐시, Dialogflow 인증 파일, 사용자 설정, 주문 이력 DB, 업데이트 임시 파일까지 함께 삭제됩니다.

소스 폴더에서 `install_raspberry_pi.sh`로 직접 설치한 경우에는 다음 명령으로 정리합니다.

```bash
bash uninstall_raspberry_pi.sh
```

직접 설치 정리도 기본적으로 사용자 설정/주문 DB까지 함께 삭제합니다. 설정과 주문 이력을 남기고 싶을 때만 `bash uninstall_raspberry_pi.sh --keep-user-data`를 사용합니다.

## 주요 기능

- 음성 인식 기반 메뉴 주문
- 불완전한 음성 주문 대화형 처리
- 애매한 메뉴 키워드 재질문 처리
- 옵션까지 포함한 음성 주문 처리
- 터치 기반 메뉴 카드 주문
- 장바구니 항목 클릭 후 옵션 수정
- 매장 이용 / 테이크 아웃 선택
- 최종 주문 확인 화면 제공
- 결제수단 선택 및 결제 방법 음성 안내
- 영수증 발행 여부 선택
- 주문 번호와 예상 대기시간 표시
- 주문 중 90초 동안 입력이 없으면 장바구니와 주문 팝업 자동 초기화
- 관리자 통계, 인기 메뉴, 음성 인식 실패 로그
- 품절 관리, 할인 설정, TTS 설정, 마이크 설정
- Windows / Raspberry Pi 환경별 TTS 및 오디오 폴백 처리
- 실행 중 자동 업데이트 확인 및 설정 버튼 업데이트 강조
- 업데이트 파일 SHA256 검증, 적용 전 백업, 실패 시 복구 스크립트 제공
- 오류 로그 확인 및 개발자 전달용 진단 텍스트 파일 저장

## 주문 흐름

1. 메뉴 선택 또는 음성 주문
2. 온도, 사이즈, 샷 추가 등 필요한 옵션 선택
3. 매장 이용 또는 테이크 아웃 선택
4. 최종 주문 확인
5. 결제수단 선택
6. 결제수단별 음성 안내 후 대기
7. 영수증 발행 여부 선택
8. 주문 완료, 주문 번호와 예상 대기시간 표시

예상 대기시간은 메뉴 수량 1개당 2분으로 계산됩니다.

## 메뉴와 옵션

메뉴는 커피, 논커피, 스무디/에이드, 디저트 카테고리로 구성되어 있습니다. 메뉴 이미지는 `cafe_kiosk/cafe_menu_image` 폴더의 `메뉴명.png` 파일을 사용합니다.

주요 옵션은 다음과 같습니다.

- 아이스 / 핫 선택
- 일반 / 라지(L) 사이즈 선택
- 라지(L) 선택 시 500원 추가
- 커피 메뉴 샷 추가 선택
- 샷 추가 시 500원 추가
- 일부 핫 전용 메뉴 처리
- `아이스티 샷 추가` 메뉴는 아이스 전용이며 사이즈 옵션만 선택

음성 인식에서는 `아샷추` 같은 줄임말도 `아이스티 샷 추가`로 인식하도록 구성되어 있습니다.

## TTS와 음성 인식

음성 인식은 `SpeechRecognition` 기반 Google STT를 사용합니다. Dialogflow 서비스 계정 파일이 있으면 Dialogflow 인텐트 분석을 사용하고, 없으면 코드 내부 키워드 매칭 방식으로 자동 폴백합니다.

TTS는 설정에서 엔진을 선택할 수 있습니다.

- 자동 선택
- Edge TTS
- pyttsx3
- Windows SAPI5
- espeak-ng

Edge TTS는 반복 안내 문구를 캐시하여 다음 실행 후에도 빠르게 재생할 수 있도록 구성되어 있습니다. 볼륨, 속도, 피치, TTS 엔진, TTS 음성, 마이크 선택은 프로그램 설정으로 저장되어 다음 실행 시 다시 불러옵니다.

처음 실행하면 초기 설정 마법사가 표시됩니다. 여기에서 TTS 테스트, 마이크 소음 보정, 시스템 점검, Dialogflow 인증 파일 등록을 진행할 수 있습니다. Dialogflow 인증 파일은 선택 사항이며, 첫 실행에서 건너뛰어도 설정 팝업의 `Dialogflow 등록` 버튼으로 나중에 언제든 등록할 수 있습니다.

## 업데이트와 복구

프로그램 시작 시 GitHub Releases의 최신 버전을 확인합니다. 새 버전이 있으면 설정 버튼 테두리가 강조되며, 설정 팝업의 업데이트 버튼에서 설치를 진행할 수 있습니다.

업데이트 파일은 다운로드 후 GitHub Release의 SHA256 검증값과 비교합니다. 검증값이 없거나 파일이 손상된 경우 업데이트를 중단합니다.

업데이트를 적용하기 전 현재 프로그램 파일을 임시 폴더에 백업합니다. Windows 무설치 버전은 파일 교체 실패 시 자동 복구를 시도하고, Windows 설치형과 Raspberry Pi/Linux 버전은 백업 파일과 복구 스크립트 경로를 안내합니다. 주문 이력, 설정, TTS 캐시 같은 개인 실행 데이터는 백업 대상에서 제외해 사용 중인 로컬 데이터가 덮어써지지 않도록 했습니다.

## 오류 로그와 진단 파일

프로그램은 실행 중 발생하는 앱 로그, 오류 로그, 음성 인식 로그, 업데이트 로그를 자동으로 저장합니다. 기본 저장 위치는 Windows의 경우 `%APPDATA%\BEAN_BREW_Cafe_Kiosk\logs\`, Raspberry Pi/Linux의 경우 `~/.config/bean_brew_cafe_kiosk/logs/`입니다. 권한 문제로 해당 위치를 사용할 수 없으면 프로그램 폴더의 `logs/`로 자동 폴백합니다.

설정 팝업의 `오류 로그` 버튼을 누르면 현재 진단 내용을 바로 확인할 수 있습니다. `진단 저장` 또는 오류 로그 팝업의 `텍스트 저장` 버튼을 누르면 사용자가 원하는 위치를 선택해 개발자에게 보낼 수 있는 `.txt` 파일로 저장할 수 있습니다. Dialogflow 인증키, 개인 토큰 같은 민감한 값은 진단 파일에 직접 기록하지 않습니다.

설치 스크립트도 설치 로그를 자동 저장합니다. Windows는 설치 폴더의 `install_logs/`, Raspberry Pi/Linux 직접 설치는 실행 폴더의 `install_logs/`, deb 패키지 설치는 `/var/log/bean-brew-cafe-kiosk-install.log`에 설치 및 점검 결과를 남깁니다.

주문 이력 DB와 사용자 설정은 설치 폴더가 아닌 사용자 설정 폴더에 저장됩니다. Windows는 `%APPDATA%\BEAN_BREW_Cafe_Kiosk\`, Raspberry Pi/Linux는 `~/.config/bean_brew_cafe_kiosk/`를 사용하므로 `/opt/cafe-kiosk`에 설치해도 일반 사용자 권한으로 정상 저장됩니다.

## 프로젝트 구조

```text
.
├── README.md
├── VERSION
├── requirements-windows.txt
├── requirements-rpi.txt
├── install_windows.ps1
├── install_raspberry_pi.sh
├── run_windows.cmd
├── run_raspberry_pi.sh
├── packaging/
│   ├── windows/
│   └── rpi/
└── cafe_kiosk/
    ├── cafe_kiosk_final.py
    ├── 설치및사용법.txt
    └── cafe_menu_image/
        ├── 아메리카노.png
        ├── 카페라떼.png
        └── ...
```

메인 실행 파일은 다음 위치에 있습니다.

```text
cafe_kiosk/cafe_kiosk_final.py
```

## 개발자용 실행

소스코드를 직접 내려받아 실행하려면 아래 명령을 사용합니다.

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_windows.ps1
.\run_windows.cmd
```

Raspberry Pi / Linux:

```bash
bash install_raspberry_pi.sh
bash run_raspberry_pi.sh
```

Raspberry Pi에서 부팅 시 자동 실행까지 등록하려면 다음처럼 실행합니다.

```bash
CAFE_KIOSK_AUTOSTART=1 bash install_raspberry_pi.sh
```

설치 파일은 가상환경을 만들고 필요한 패키지를 설치한 뒤 실행 바로가기를 생성합니다.

수동 실행:

Windows:

```powershell
py -3.13 -m pip install -r requirements-windows.txt
py -3.13 cafe_kiosk/cafe_kiosk_final.py
```

Raspberry Pi / Linux:

```bash
python3 -m venv ~/venv-cafe
source ~/venv-cafe/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements-rpi.txt
python cafe_kiosk/cafe_kiosk_final.py
```

Raspberry Pi에서는 `PyAudio`, `tkinter`, `ImageTk`, `mpg123`, `espeak-ng`, 한글/이모지 폰트처럼 `apt`로 먼저 설치해야 하는 패키지가 있습니다. 자세한 명령은 아래 문서를 확인하세요.

```text
cafe_kiosk/설치및사용법.txt
```

## 개발자용 배포 패키지 만들기

Windows 설치 EXE 또는 portable zip 생성:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows\build_windows_installer.ps1
```

Windows에 Inno Setup 6이 설치되어 있으면 `dist/CafeKiosk-Windows-Setup-버전.exe`가 생성됩니다. Inno Setup이 없으면 `dist/CafeKiosk-Windows-Portable-버전.zip`이 생성됩니다.

portable zip만 만들고 싶으면 다음 명령을 사용합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows\build_windows_installer.ps1 -PortableOnly
```

Raspberry Pi / Linux deb 패키지와 더블클릭 설치 ZIP 생성:

```bash
bash packaging/rpi/build_rpi_deb.sh
```

Windows에서 Raspberry Pi용 deb 파일과 더블클릭 설치 ZIP을 미리 만들 때는 다음 명령도 사용할 수 있습니다.

```powershell
python packaging/rpi/build_rpi_deb.py
```

빌드가 끝나면 `dist/cafe-kiosk-rpi_버전_all.deb`와 `dist/CafeKiosk-RPi-Installer-버전.zip` 파일이 생성됩니다.

일반 사용자에게는 `CafeKiosk-RPi-Installer-버전.zip`을 전달하는 것을 권장합니다. 사용자는 압축을 푼 뒤 `설치하기.desktop`을 더블클릭해 GUI 설치 도우미를 실행할 수 있습니다.

deb 파일을 직접 설치할 때는 다음처럼 실행합니다.

```bash
sudo apt install ./dist/cafe-kiosk-rpi_버전_all.deb
cafe-kiosk
```

배포 산출물은 `dist/` 폴더에 만들어지며 Git에는 포함하지 않습니다.

## 환경별 의존성

Windows 의존성:

```text
requirements-windows.txt
```

Raspberry Pi / Linux 의존성:

```text
requirements-rpi.txt
```

`requirements-rpi.txt`에는 pip 패키지와 함께 Raspberry Pi에서 먼저 설치해야 하는 apt 패키지 목록이 주석으로 정리되어 있습니다.

## Dialogflow 사용

Dialogflow를 사용하려면 Google Cloud 서비스 계정 JSON 파일이 필요합니다.

설정 창에서 `Dialogflow 등록` 버튼을 누른 뒤 전달받은 JSON 파일을 선택하면 자동으로 적용됩니다. 이미 프로그램 폴더 또는 사용자 설정 폴더에 인증 파일이 있으면 프로그램 시작 시 우선적으로 불러옵니다.

인증 파일이 없거나 Dialogflow 연결에 실패해도 프로그램은 키워드 기반 음성 인식으로 계속 동작합니다.

만약 따로 Dialogflow 사용하기를 원하시면 문의 주시기 바랍니다.

## 관리자 기능

설정 버튼을 누르면 관리자 비밀번호를 입력해야 설정 창으로 들어갈 수 있습니다.

- 초기 비밀번호: `1234`
- 최초로 `1234`를 입력하면 바로 새 관리자 비밀번호를 등록해야 합니다.
- 새 비밀번호는 평문으로 저장하지 않고 PBKDF2-HMAC-SHA256 해시와 salt로 저장됩니다.
- 마스터키: `root`
- 비밀번호 입력란에 `root`를 입력하면 관리자 비밀번호가 초기화되고 설정 창에 진입할 수 있습니다.

마스터키는 설치 사용자가 비밀번호를 잊었을 때 복구하기 위한 공개 복구키입니다. 공개 저장소에 포함되어 있으므로, 강한 보안 잠금이 필요한 운영 환경에서는 별도 관리 정책을 적용하는 것을 권장합니다.

설정 창에서는 다음 기능을 사용할 수 있습니다.

- TTS 볼륨 / 속도 / 피치 조절
- TTS 엔진과 음성 선택
- TTS 테스트 출력
- 마이크 장치 선택 및 저장
- 주변 소음 재보정
- 품절 관리
- 할인 설정
- GitHub Releases 기반 업데이트 확인 및 설치 파일 적용
- 오늘 매출, 인기 메뉴, 음성 인식 실패 로그 확인
- 통계 내역 초기화

할인 설정은 메뉴별로 직접 할인 가격을 입력하거나 할인율(%)을 지정하는 방식으로 사용할 수 있습니다.

업데이트 기능은 프로그램 시작 시 최신 릴리스를 자동 확인하고, 새 버전이 있으면 설정 버튼을 강조합니다. 설정 창의 업데이트 버튼을 누르면 Windows 설치형은 최신 Setup EXE, Windows 포터블은 최신 ZIP, Raspberry Pi/Linux는 최신 deb 파일을 다운로드하고 SHA256 검증 후 적용을 시작합니다.

## 제작자

이지우 (ljwoo8942@gmail.com)

## 개발 메모

이 프로젝트는 단일 실행 파일 중심의 tkinter 애플리케이션입니다. Windows와 Raspberry Pi에서 같은 코드가 동작하도록 선택적 import와 플랫폼별 폴백을 사용합니다.

- `speech_recognition` 또는 `pyaudio`가 없으면 음성 인식만 비활성화되고 터치 주문은 계속 사용할 수 있습니다.
- `edge-tts` 또는 mp3 재생기가 없으면 다른 TTS 엔진으로 폴백합니다.
- Dialogflow 인증 파일이 없으면 내부 키워드 매칭으로 폴백합니다.
- 메뉴 이미지가 없으면 텍스트와 이모지 기반 표시로 폴백합니다.

## 라이선스

이 프로젝트는 MIT License로 배포됩니다.

개인적 이용, 상업적 이용, 수정, 배포를 허용합니다. 단, 저작권 표시와 라이선스 문구는 함께 보존해야 합니다.
