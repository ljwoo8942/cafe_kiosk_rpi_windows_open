# Cafe Kiosk RPi Windows Open

음성 인식과 음성 안내를 중심으로 만든 접근성 지향 카페 키오스크입니다. 일반 터치 키오스크 사용이 어려운 노약자분들도 메뉴, 옵션, 주문 확인, 결제 진행을 음성 안내에 따라 차근차근 진행할 수 있도록 설계했습니다.

터치 주문도 함께 지원하지만, 핵심 목표는 사용자가 메뉴와 옵션을 말하면 프로그램이 부족한 정보를 다시 질문하고 주문을 완성해 주는 대화형 음성 주문 흐름입니다.

## 지원 환경

- Windows 10 / 11
- Raspberry Pi OS / Linux
- Python 3.13.12 기준으로 개발 및 테스트
- Raspberry Pi 5인치 / 7인치 터치 디스플레이 구성 지원

Raspberry Pi에서는 `xrandr`로 연결된 모니터 크기와 위치를 감지해 작은 화면은 음성+터치 주문 창, 큰 화면은 키오스크 주문 창으로 자동 배치합니다. 단일 소형 화면에서는 탭 기반 풀스크린 UI로 실행됩니다.

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
- 관리자 통계, 인기 메뉴, 음성 인식 실패 로그
- 품절 관리, 할인 설정, TTS 설정, 마이크 설정
- Windows / Raspberry Pi 환경별 TTS 및 오디오 폴백 처리

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

Edge TTS는 반복 안내 문구를 `cafe_kiosk/tts_cache`에 캐시하여 다음 실행 후에도 빠르게 재생할 수 있도록 구성되어 있습니다. 볼륨, 속도, 피치, TTS 엔진, TTS 음성, 마이크 선택은 `cafe_kiosk/cafe_kiosk_settings.json`에 저장되어 다음 실행 시 다시 불러옵니다.

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

## 빠른 실행

간편 설치를 원하는 경우 아래 설치 파일을 먼저 실행하세요.

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

## 배포 패키지 만들기

Windows 설치 EXE 또는 portable zip 생성:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows\build_windows_installer.ps1
```

Windows에 Inno Setup 6이 설치되어 있으면 `dist/CafeKiosk-Windows-Setup-버전.exe`가 생성됩니다. Inno Setup이 없으면 `dist/CafeKiosk-Windows-Portable-버전.zip`이 생성됩니다.

portable zip만 만들고 싶으면 다음 명령을 사용합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows\build_windows_installer.ps1 -PortableOnly
```

Raspberry Pi / Linux deb 패키지 생성:

```bash
bash packaging/rpi/build_rpi_deb.sh
```

빌드가 끝나면 `dist/cafe-kiosk-rpi_버전_all.deb` 파일이 생성됩니다. Raspberry Pi에서 설치할 때는 다음처럼 실행합니다.

```bash
sudo apt install ./dist/cafe-kiosk-rpi_버전_all.deb
cafe-kiosk
```

배포 산출물은 `dist/` 폴더에 만들어지며 Git에는 포함하지 않습니다.

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

Dialogflow를 사용하려면 Google Cloud 서비스 계정 JSON 파일을 `cafe_kiosk` 폴더에 배치해야 합니다. 현재 코드는 기본 파일명으로 `avis-fcwa-d608a6b1f702.json`을 찾습니다.

이 파일은 개인 인증 정보이므로 저장소에 포함하지 않습니다. 파일이 없어도 프로그램은 키워드 기반 음성 인식으로 동작합니다.

만약 따로 Dialogflow 사용하기를 원하시면 문의 주시기 바랍니다.

## 저장되지 않는 로컬 파일

아래 파일은 실행 중 자동 생성되거나 개인 환경에 따라 달라지므로 Git에 올리지 않습니다.

- `cafe_kiosk/cafe_kiosk.db`
- `cafe_kiosk/cafe_kiosk_settings.json`
- `cafe_kiosk/tts_cache/`
- `cafe_kiosk/*.json`
- `__pycache__/`
- 가상환경 폴더

데이터베이스에는 주문 이력, 메뉴 키워드, 음성 인식 실패 로그 등이 저장됩니다. 공개 저장소에는 샘플 코드와 기본 리소스만 포함합니다.

## 관리자 기능

설정 창에서 다음 기능을 사용할 수 있습니다.

- TTS 볼륨 / 속도 / 피치 조절
- TTS 엔진과 음성 선택
- TTS 테스트 출력
- 마이크 장치 선택 및 저장
- 주변 소음 재보정
- 품절 관리
- 할인 설정
- GitHub 업데이트 확인 및 적용
- 오늘 매출, 인기 메뉴, 음성 인식 실패 로그 확인
- 통계 내역 초기화

할인 설정은 메뉴별로 직접 할인 가격을 입력하거나 할인율(%)을 지정하는 방식으로 사용할 수 있습니다.

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
