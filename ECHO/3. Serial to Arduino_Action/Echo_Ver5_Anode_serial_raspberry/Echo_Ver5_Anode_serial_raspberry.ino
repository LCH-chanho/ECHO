// === 아두이노: Servo는 Servo.h / RGB는 Soft PWM ===

#include <Servo.h>

// === 서보 객체 선언 ===
Servo servo1;  // Siren 용
Servo servo2;  // Horn 용

// === 서보 핀 매핑 ===
#define SERVO_SIREN 3   // Siren 서보 모터 핀
#define SERVO_HORN  9   // Horn 서보 모터 핀

// === RGB LED 핀 설정 (소프트 PWM) ===
#define LED1_R 10
#define LED1_G 11
#define LED1_B 12
#define LED2_R A0
#define LED2_G A1
#define LED2_B A2

// === 사운드 타입 정의 (라즈베리 CLASS_ID_MAP과 일치) ===
#define SOUND_INIT   "INIT"
#define SOUND_NONE   "NONE"
#define SOUND_SIREN  "SIREN"
#define SOUND_HORN   "HORN"

// === 상태 변수 ===
int detectedSound = SOUND_NONE;
unsigned long lastChangeTime = 0;
int patternPhase = 0;
unsigned long lastUpdate = 0;
bool soundActive = false;
unsigned long detectedStartTime = 0;

// === 감지 후 7초 동작 보증 변수 ===
bool eventLock = false; //True면 다른이벤트 무시
unsigned long eventStartTime = 0; //동작시간 체크
const unsigned long EVENT_DURATION = 7000;  // 7초

// 혼 패턴용 변수
bool hornBurst = true;
unsigned long hornStart = 0;
unsigned long hornTimer = 0;
bool hornToggle = false;

// 사이렌 순환 패턴
static bool directionRightFirst = true;
static int sirenPatternStep = 0; // 소방→경찰→응급 순서 전환
static int sirenRepeatCounter = 0; // 각 패턴 반복 횟수 누적

// INIT 패턴용 변수
bool initMode = false;
unsigned long initStartTime = 0;
int initPhase = 0;
unsigned long initPhaseTime = 0;

// === LED 버스트 상태 구조체 ===
struct BurstState {
  unsigned long timer = 0;
  int count = 0;
};
BurstState burstCH1, burstCH2;

// === LED 채널 제어 함수 (Anode 타입 반전) ===
void setLED_CH1(int r, int g, int b) {
  analogWrite(LED1_R, 255 - r);
  analogWrite(LED1_G, 255 - g);
  analogWrite(LED1_B, 255 - b);
}
void setLED_CH2(int r, int g, int b) {
  analogWrite(LED2_R, 255 - r);
  analogWrite(LED2_G, 255 - g);
  analogWrite(LED2_B, 255 - b);
}

// === 버스트 초기화 ===
void resetBursts() {
  burstCH1.count = 0;
  burstCH2.count = 0;
  setLED_CH1(0, 0, 0);
  setLED_CH2(0, 0, 0);
}

// === LED 버스트 함수 ===
void burst(int ch, int r, int g, int b, int repeat = 6, int speed = 30) {
  BurstState* bs = (ch == 1) ? &burstCH1 : &burstCH2;
  if (millis() - bs->timer >= speed) {
    bs->timer = millis();
    bool on = (bs->count % 2 == 0);
    if (ch == 1) setLED_CH1(on ? r : 0, on ? g : 0, on ? b : 0);
    else         setLED_CH2(on ? r : 0, on ? g : 0, on ? b : 0);
    bs->count++;
    if (bs->count >= repeat * 2) {
      bs->count = 0;
      if (ch == 1) setLED_CH1(0, 0, 0);
      else         setLED_CH2(0, 0, 0);
    }
  }
}

// === 서보 동작 함수 ===
void wiggleServo(Servo& servo) {
  static bool dir = false;
  int angle = dir ? 0 : 90;
  servo.write(angle);
  dir = !dir;
}

void handleServo(int type, unsigned long now) {
  static unsigned long lastServoTime = 0;
  static int lastType = -1;
  if (type == SOUND_NONE || !soundActive) return;
  if (type != lastType) {
    lastType = type;
    lastServoTime = now;
  }
  if (now - lastServoTime < 500) return;
  lastServoTime = now;
  if (type == SOUND_SIREN) wiggleServo(servo1);
  else if (type == SOUND_HORN) wiggleServo(servo2);
}

// === LED 패턴 처리 함수 ===
void handleLEDPattern(int type, unsigned long now);



// === 시리얼 입력 처리 ===
void checkSerialInput() {
  if (Serial.available() > 0) {
    String inputStr = Serial.readStringUntil('\n');
    inputStr.trim(); //공백 제거

    Serial.println("[RECEIVED] 시리얼 입력: " + inputStr);

    // INIT은 eventLock과 무관하게 수신 가능
    if (inputStr == SOUND_INIT) {
      if (!initMode) {
        initMode = true;
        initStartTime = millis();
        initPhase = 0;
        initPhaseTime = millis();
        Serial.println("[STATE] INIT → 초기 패턴 시작");
      } else {
        Serial.println("[STATE] 중복 INIT 무시됨");
      }
      return;
    }

    // 이벤트 잠금 상태에서는 NONE/SIREN/HORN 무시
    if (eventLock && inputStr != SOUND_INIT) {
      Serial.println("[BLOCKED] 7초 내 입력 무시됨");
      return;
    }

    // NONE
    if (inputStr == SOUND_NONE) {
      soundActive = false;
      detectedSound = SOUND_NONE;
      resetBursts();
      Serial.println("[STATE] NONE → 모든 동작 정지");
    }
    // SIREN
    else if (inputStr == SOUND_SIREN) {
      eventLock = true;
      eventStartTime = millis();

      soundActive = true;
      detectedSound = SOUND_SIREN;
      detectedStartTime = millis();
      resetBursts();
      patternPhase = 0;
      sirenPatternStep = 0;
      sirenRepeatCounter = 0;
      Serial.println("[STATE] SIREN → 시각/서보 동작 시작");
    }
    // HORN
    else if (inputStr == SOUND_HORN) {
      eventLock = true;
      eventStartTime = millis();

      soundActive = true;
      detectedSound = SOUND_HORN;
      detectedStartTime = millis();
      resetBursts();
      patternPhase = 0;
      sirenPatternStep = 0;
      sirenRepeatCounter = 0;
      Serial.println("[STATE] HORN → 시각/서보 동작 시작");
    }
    else {
      Serial.println("[WARNING] 유효하지 않은 문자열 수신: " + inputStr);
    }
  }
}

// === INIT 시퀀스 ===
void handleInitPattern(unsigned long now) {
  if (initPhase == 0 && now - initPhaseTime > 1000) {
    setLED_CH1(255, 0, 0); setLED_CH2(255, 0, 0);  // 빨강
    Serial.println("[INIT] 빨강 표시");
    initPhase = 1; initPhaseTime = now;
  } else if (initPhase == 1 && now - initPhaseTime > 1000) {
    setLED_CH1(0, 0, 255); setLED_CH2(0, 0, 255);  // 파랑
    Serial.println("[INIT] 파랑 표시");
    initPhase = 2; initPhaseTime = now;
  } else if (initPhase == 2 && now - initPhaseTime > 1000) {
    setLED_CH1(0, 255, 0); setLED_CH2(0, 255, 0);  // 초록
    Serial.println("[INIT] 초록 표시");
    initPhase = 3; initPhaseTime = now;
  } else if (initPhase >= 3) {
    unsigned long elapsed = now - initPhaseTime;
    int g = (elapsed / 500) % 2 == 0 ? 255 : 0;  // 0.5초마다 ON/OFF 토글
    setLED_CH1(0, g, 0); setLED_CH2(0, g, 0);
    if (g == 255) Serial.println("[INIT] 깜빡임 초록 ON");
    else Serial.println("[INIT] 깜빡임 초록 OFF");

    if (elapsed > 4500) {  // 총 2.5초 (5회 깜빡임) 후 종료
      setLED_CH1(0, 0, 0); setLED_CH2(0, 0, 0);
      initMode = false;
      Serial.println("[INIT] 완료 및 종료");
    }
  }
}


// === 메인 루프 ===
void loop() {
  unsigned long now = millis();

  // 7초 이벤트 락 해제 조건
  if (eventLock && (now - eventStartTime >= EVENT_DURATION)) {
    eventLock = false;
    Serial.println("[UNLOCKED] 7초 이벤트 종료 → 다음 입력 수락 가능");
  }

  checkSerialInput();

  if (initMode) {
    handleInitPattern(now);
    return;
  }

  if (soundActive && detectedSound == SOUND_SIREN) {
    handleLEDPattern(SOUND_SIREN, now);
    handleServo(SOUND_SIREN, now);
  } else if (soundActive && detectedSound == SOUND_HORN) {
    handleLEDPattern(SOUND_HORN, now);
    handleServo(SOUND_HORN, now);
  } else if (detectedSound == SOUND_NONE) {
    setLED_CH1(0, 0, 0);
    setLED_CH2(0, 0, 0);
  }
}

void handleLEDPattern(int type, unsigned long now) {
  if (!soundActive) return;
  if (type == SOUND_HORN) {
    if (hornBurst && now - hornStart > 1000) {
      hornBurst = false;
      hornStart = now;
      hornToggle = false;
      resetBursts();
    } else if (!hornBurst && now - hornStart > 3000) {
      hornBurst = true;
      hornStart = now;
      resetBursts();
    }
    if (hornBurst) {
      burst(1, 255, 255, 0);
      burst(2, 255, 255, 0);
    } else {
      if (now - hornTimer >= 300) {
        hornToggle = !hornToggle;
        hornTimer = now;
        int val = hornToggle ? 255 : 0;
        setLED_CH1(val, val, 0);
        setLED_CH2(val, val, 0);
      }
    }
  }
  else if (type == SOUND_SIREN) {
    if (sirenPatternStep == 0) {
      if (now - lastUpdate > 500) {
        lastUpdate = now;
        patternPhase = (patternPhase + 1) % 2;
        resetBursts();
        sirenRepeatCounter++;
      }
      if (patternPhase == 0) burst(1, 255, 0, 0);
      else burst(2, 255, 0, 0);
      if (sirenRepeatCounter >= 4) {
        sirenPatternStep = 1;
        sirenRepeatCounter = 0;
        patternPhase = 0;
      }
    } else if (sirenPatternStep == 1) {
      if (now - lastUpdate > 500) {
        lastUpdate = now;
        patternPhase = (patternPhase + 1) % 2;
        resetBursts();
        sirenRepeatCounter++;
      }
      if (patternPhase == 0) {
        burst(1, 0, 0, 255);
        burst(2, 255, 0, 0);
      } else {
        burst(1, 255, 0, 0);
        burst(2, 0, 0, 255);
      }
      if (sirenRepeatCounter >= 4) {
        sirenPatternStep = 2;
        sirenRepeatCounter = 0;
        patternPhase = 0;
      }
    } else {
      if (now - lastUpdate > 500) {
        lastUpdate = now;
        patternPhase = (patternPhase + 1) % 3;
        if (patternPhase == 0) directionRightFirst = !directionRightFirst;
        resetBursts();
        sirenRepeatCounter++;
      }
      if (patternPhase == 0) {
        if (directionRightFirst) burst(2, 0, 255, 0);
        else burst(1, 0, 255, 0);
      } else if (patternPhase == 1) {
        if (directionRightFirst) burst(1, 0, 255, 0);
        else burst(2, 0, 255, 0);
      } else {
        burst(1, 0, 255, 0);
        burst(2, 0, 255, 0);
      }
      if (sirenRepeatCounter >= 6) {
        sirenPatternStep = 0;
        sirenRepeatCounter = 0;
        patternPhase = 0;
      }
    }
  }
}



void setup() {
  Serial.begin(9600);
  pinMode(LED1_R, OUTPUT);
  pinMode(LED1_G, OUTPUT);
  pinMode(LED1_B, OUTPUT);
  pinMode(LED2_R, OUTPUT);
  pinMode(LED2_G, OUTPUT);
  pinMode(LED2_B, OUTPUT);
  servo1.attach(SERVO_SIREN);
  servo2.attach(SERVO_HORN);
  setLED_CH1(0, 0, 0);
  setLED_CH2(0, 0, 0);

  // === 라즈베리로부터 핸드셰이크 대기 ===
  while (!Serial);  // USB 연결 대기
  delay(1000);      // 안정화 대기

  while (true) {
    if (Serial.available() > 0) {
      String msg = Serial.readStringUntil('\n');
      if (msg == "ping") {
        Serial.println("pong");
        break; // 확인되면 루프 빠져나감
      }
    }
  }

}
