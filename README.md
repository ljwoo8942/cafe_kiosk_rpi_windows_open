# Cafe Kiosk RPi Windows Open

이 프로그램은 키오스크 사용이 어려우신 노약자분들을 위해 만든 음성 인식과 음성 안내 주문 위주의 카페 키오스크입니다.

터치 주문도 지원하지만, 핵심 목적은 사용자가 메뉴와 옵션을 음성으로 말하고 프로그램이 음성 안내를 통해 주문 과정을 대화형으로 진행하도록 돕는 것입니다.

## 지원 환경

- Windows
- Raspberry Pi OS / Linux
- Python 3.13.12

## 주요 기능

- 음성 인식 기반 메뉴 주문
- 음성 안내 TTS 주문 진행
- 터치 기반 키오스크 주문
- 매장 이용 / 테이크 아웃 선택
- 온도, 사이즈, 샷 추가 등 음료 옵션 선택
- 결제수단 선택 및 결제 안내 음성 출력
- 영수증 발행 여부 선택
- 주문 완료 팝업 및 예상 대기시간 표시
- 관리자 통계, 품절 관리, 할인 설정
- Windows / Raspberry Pi 환경별 TTS 및 오디오 처리

## 실행 파일

메인 실행 파일은 다음 위치에 있습니다.

```text
cafe_kiosk/cafe_kiosk_final.py
```

## 설치 안내

환경별 의존성 파일은 다음과 같습니다.

```text
requirements-windows.txt
requirements-rpi.txt
```

자세한 설치 및 사용 방법은 아래 문서를 참고하세요.

```text
cafe_kiosk/설치및사용법.txt
```
