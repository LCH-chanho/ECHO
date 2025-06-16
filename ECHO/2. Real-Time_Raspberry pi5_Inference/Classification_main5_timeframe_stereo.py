# gamma_cnn_main5_timeframe.py를 모델로 사용한다.
# 라즈베리의 제한적 라이브러리(Numpy) 버전으로인해 batch사용, h5형식 모델 사용에 제한이있다.
# 따라서 폴더구조의 모델을 불러와 사용하며 해당 경로를 path에 복사하여 사용한다.


import os
import numpy as np
import tensorflow as tf
import sounddevice as sd
from gammatone.gtgram import gtgram
import time
import serial
import librosa #리샘플링용 

# 정확한 디바이스 지정(입력 전용)
sd.default.device = (1, None) 

print("사용중인 오디오장치: ", sd.query_devices(sd.default.device[0]))


# === 모델 및 파라미터 설정 ===
#MODEL_PATH = "gamma_cnn_main5_timeframe.h5"
MODEL_PATH = "/home/pi/myProjects/echo/Ver4/gamma_cnn_main5_timeframe"  # 폴더형태 모델 경로

CLASS_NAMES = ['Horn', 'None', 'Siren']

CLASS_ID_MAP = {
    'INIT': "INIT", #문자열전송 
    'None': "NONE",
    'Siren': "SIREN",
    'Horn': "HORN"
}

# === 오디오 파라미터 ===
MIC_SAMPLE_RATE = 48000 #마이크 입력 샘플레이트
MODEL_SAMPLE_RATE = 44100 #학습 모델 샘플레이트 기준
SAMPLE_RATE = MIC_SAMPLE_RATE

CHANNELS = 2
DTYPE = 'int32'
WIN_TIME = 0.025
HOP_TIME = 0.010
N_FILTERS = 64
FMIN = 50

SEGMENT_SECONDS = 0.6
SAMPLES_PER_SEGMENT = int(MIC_SAMPLE_RATE * SEGMENT_SECONDS)
TARGET_TIME_FRAMES = int(SEGMENT_SECONDS / HOP_TIME) #→ 0.6 / 0.01 = 60

# === 아두이노 연결 설정 ===
ARDUINO_PORT = '/dev/ttyUSB0'  # NANO 실제 포트에 맞게 수정
#ARDUINO_PORT = '/dev/ttyACM0' #Uno
BAUDRATE = 9600

try:
    arduino = serial.Serial(ARDUINO_PORT, BAUDRATE)
    time.sleep(5) #아두이노 초기화 대기
    print(f"[✅ 아두이노 연결됨] 포트: {ARDUINO_PORT}")
except Exception as e:
    print(f"[❌ 아두이노 연결 실패]: {e}")
    arduino = None
    

# === 모델 로드 ===
model = tf.keras.models.load_model(MODEL_PATH)


# === 전처리 함수 ===
def preprocess_segment(segment):
    # 감마톤 변환 + log 정규화
    gtg = gtgram(segment, MODEL_SAMPLE_RATE, WIN_TIME, HOP_TIME, N_FILTERS, FMIN)
    gtg = np.log(gtg + 1e-6)

    # 프레임 수 맞추기(정규화) (pad/crop)
    if gtg.shape[1] < TARGET_TIME_FRAMES: # → 60
        pad = np.zeros((gtg.shape[0], TARGET_TIME_FRAMES - gtg.shape[1]))
        gtg = np.concatenate([gtg, pad], axis=1)
    elif gtg.shape[1] > TARGET_TIME_FRAMES:
        gtg = gtg[:, :TARGET_TIME_FRAMES]

    return gtg[..., np.newaxis]  # (64, N, 1)


# === serial 정상연결 확인 핸드셰이크 ===
def handshake_with_arduino():
    if not arduino:
        print("[아두이노 없음]")
        return False
    
    print("[핸드셰이크 시작]")
    for attempt in range(10): #최대 10번 시도(약5초)
        arduino.write(b'ping\n')
        time.sleep(0.5)
        if arduino.in_waiting > 0:
            try:
                response = arduino.readline().decode('utf-8').strip()
                if response == 'pong':
                    print("[핸드셰이크  성공!]")
                    return True
            except:
                pass
        print("[핸드셰이크 실패]")
        return False


# === INIT 신호 전송 (핸드셰이크 성공시에만 INIT 1회 전송) ===
if handshake_with_arduino():
    arduino.write(f"{CLASS_ID_MAP['INIT']}\n".encode())  # "INIT\n"
    print("[INIT 전송됨]")
    time.sleep(0.5) #안정화 대기
    arduino.reset_input_buffer()


# === 예측 결과 히스토리 관리 ===
prev_class = None
repeat_count = 0

def send_if_repeated(pred_class, pred_prob):
    global prev_class, repeat_count
    
    #클래스별 threshold 정의
    class_thresholds = {
        'Horn': 0.94,
        'Siren': 0.94,
        'None': 0.85,
    }
    
    #현재 클래스의 임계값 가져오기
    threshold = class_thresholds.get(pred_class, 0.80) # 혹시 없는 경우는 기본값 0.80
    
    # 확률이 threshold보다 낮으면 감지 취소
    if pred_prob < threshold:
        repeat_count = 0 #확률 저하부분도 카운트 리셋
        prev_class = None
        return
    
    #반복 감지 확인
    if pred_class == prev_class: #과거 값과 같으면 1증가
        repeat_count += 1
    else:
        repeat_count = 1 #과거값과 다르면 그대로 1유지
        prev_class = pred_class #이전값에 갱신된값으로 넣기

    if repeat_count == 2 and arduino: #2번연속 감지 시
        code = CLASS_ID_MAP.get(pred_class, -1) #글자에 맞는 문자열 가져오기
        if code != -1:
            arduino.write(f"{code}\n".encode())
            print(f"[아두이노 전송] {pred_class} → {code}")
            repeat_count = 0
        
        
# === 실시간 입력을 위한 콜백 ===
buffer = []

def record_callback(indata, frames, time_, status):
    global buffer
    if status:
        print(f"[경고] {status}")
    buffer.extend(indata[:, 0])  # 1채널 기준
    
# === 실시간 스트림 시작 ===
def monitor_arduino_feedback():
    if not arduino:
        return
    try:
        while arduino.in_waiting > 0:
            arduino.readline() #읽고 무시
            #line = arduino.readline().decode('utf-8', errors='ignore').strip()
            #if line:
            #    print(f"[아두이노 수신] {line}")
    except:
        pass
       
    
    
# === 실시간 스트림 시작 ===
print("실시간 스트리밍 시작 (Ctrl+C로 종료)...")


with sd.InputStream(samplerate=MIC_SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE,
                    callback=record_callback, blocksize=SAMPLES_PER_SEGMENT):
    try:
        while True:
            monitor_arduino_feedback()
            if len(buffer) >= SAMPLES_PER_SEGMENT:
                # 세그먼트 추출
                segment = np.array(buffer[:SAMPLES_PER_SEGMENT])
                segment = segment.astype(np.float32)
                segment = segment / (2**31) #int32
                segment = segment * 0.1
                buffer = buffer[SAMPLES_PER_SEGMENT:]
                
                #리샘플링: 48000Hz -> 44100Hz
                segment = librosa.resample(segment, orig_sr=MIC_SAMPLE_RATE, target_sr=MODEL_SAMPLE_RATE)
                #print(f"[segment range] min: {segment.min():.6f}, max: {segment.max():.6f}")

                # 전처리 및 예측
                input_data = preprocess_segment(segment)
                input_data = np.expand_dims(input_data, axis=0)  # (1, 64, N, 1)
                pred = model.predict(input_data, verbose=0) # (1,3)
                #print(f"[DEBUG] 예측 shape: {pred.shape}")
                pred = pred[0] # ->(3, )
                pred_index = np.argmax(pred)
                pred_class = CLASS_NAMES[np.argmax(pred)] #예측된 숫자의 문자를 저장
                pred_prob = pred[pred_index]
                
                print(f"[Detected] {pred_class} ({pred_prob:.2f})")
                send_if_repeated(pred_class, pred_prob)
                
    except KeyboardInterrupt:
        print("스트리밍 종료")
