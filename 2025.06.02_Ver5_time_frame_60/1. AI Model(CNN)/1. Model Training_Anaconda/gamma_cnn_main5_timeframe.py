# No: main 5
# Time Frame : 0.6초
# activation Function : relu
# CNN모델 : 경량화
# 공통 compile 변수 : optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'] / epochs=15, batch_size=64
# [결과] 정확도 98%

# === 라이브러리 임포트 ===
import os
import librosa
import numpy as np
import random
from glob import glob
from tqdm import tqdm
import tensorflow as tf
from sklearn.model_selection import train_test_split
from tensorflow.keras import layers, models
from gammatone.gtgram import gtgram
import multiprocessing as mp

# === 하이퍼파라미터 설정 ===
SAMPLE_RATE = 44100             # 오디오 샘플레이트 (Hz)
WIN_TIME = 0.025                # 감마톤 윈도우 길이 (초)
HOP_TIME = 0.010                # 감마톤 프레임 간격 (초)
N_FILTERS = 64                  # 감마톤 필터 개수
FMIN = 50                       # 최소 주파수 (Hz)
SEGMENT_SECONDS = 0.6          # 세그먼트 길이 (초) 0.6, 0.7, 0.8 0.9
SAMPLES_PER_SEGMENT = int(SEGMENT_SECONDS * SAMPLE_RATE)  # 세그먼트당 샘플 수
TARGET_TIME_FRAMES = int(SEGMENT_SECONDS / HOP_TIME)      # 프레임 수 (예: 1.0 / 0.01 = 100)
MAX_SEGMENTS_PER_FILE = 5      # 파일당 최대 세그먼트 수 제한
MAX_FILES_PER_CLASS = 5000     # 클래스당 최대 파일 수
CPU_COUNT = 8                  # 병렬 처리 시 CPU 코어 수
CLASS_NAMES = ['Horn', 'None', 'Siren']  # 분류할 클래스 이름들

# === 오디오 파일 1개를 감마톤 세그먼트 여러 개로 변환하는 함수 ===
def process_audio_file(args):
    path, label_idx = args
    try:
        y, sr = librosa.load(path, sr=SAMPLE_RATE)  # 오디오 로드
        duration = len(y) / sr
        if duration < SEGMENT_SECONDS:
            return []  # 너무 짧은 파일은 제외

        segments = []
        seg_count = 0
        for i in range(0, len(y) - SAMPLES_PER_SEGMENT + 1, SAMPLES_PER_SEGMENT):
            if seg_count >= MAX_SEGMENTS_PER_FILE:
                break

            y_seg = y[i:i + SAMPLES_PER_SEGMENT]  # 1초 단위 슬라이싱
            gtg = gtgram(y_seg, sr, WIN_TIME, HOP_TIME, N_FILTERS, FMIN)  # 감마톤 변환
            gtg = np.log(gtg + 1e-6)  # 로그 정규화 (논문 방식)

            if gtg.shape[1] < TARGET_TIME_FRAMES-10: #프레임 자동계산1
                continue  # 프레임 수 부족 시 제외

            # 프레임 수 맞추기 (pad or crop)
            if gtg.shape[1] < TARGET_TIME_FRAMES: #프레임 자동계산2
                pad = np.zeros((gtg.shape[0], TARGET_TIME_FRAMES - gtg.shape[1])) #프레임 자동계산3
                gtg = np.concatenate([gtg, pad], axis=1)
            elif gtg.shape[1] > TARGET_TIME_FRAMES: #프레임 자동계산4
                gtg = gtg[:, :TARGET_TIME_FRAMES] #프레임 자동계산5
                

            segments.append((gtg[..., np.newaxis], label_idx))  # 채널 차원 추가 후 저장
            seg_count += 1

        return segments

    except Exception as e:
        print(f"[❌ 오류] {path} → {str(e)}")
        return []

# === 전체 파이프라인 ===
def main():
    gpus = tf.config.list_physical_devices('GPU')
    print(f"[GPU]: {gpus if gpus else '❌ 사용 불가. CPU 사용 중'}")

    BASE_PATH = r"D:\\AIhub_Data\\dataset_3class\\Training"      # 학습용 오디오 파일 경로
    SAVE_PATH = r"D:\\AIhub_Data\\dataset_3class\\npy_saved5"     # npy 및 모델 저장 경로
    os.makedirs(SAVE_PATH, exist_ok=True)

    file_label_pairs = []
    file_counts = {}
    for idx, label in enumerate(CLASS_NAMES):
        files = glob(os.path.join(BASE_PATH, label, "**", "*.wav"), recursive=True)
        random.shuffle(files)
        files = files[:MAX_FILES_PER_CLASS]
        file_counts[label] = len(files)
        file_label_pairs.extend([(f, idx) for f in files])

    print(f"\n[⚡ 감마톤 변환 시작 - 총 파일 수: {len(file_label_pairs)}개]\n")
    with mp.Pool(processes=CPU_COUNT) as pool:
        results = list(tqdm(pool.imap_unordered(process_audio_file, file_label_pairs),
                            total=len(file_label_pairs)))

    # === 결과 통합 ===
    X_all, y_all = [], []
    for segments in results:
        for x, y in segments:
            X_all.append(x)
            y_all.append(y)

    # === Numpy 배열로 변환 및 저장 ===
    X_final = np.array(X_all)
    y_final = np.array(y_all)
    np.save(os.path.join(SAVE_PATH, "X_data.npy"), X_final)
    np.save(os.path.join(SAVE_PATH, "y_data.npy"), y_final)
    print("[✅ 데이터 저장 완료] X:", X_final.shape, "/ y:", y_final.shape)

    # === 데이터 분할 ===
    X_train, X_val, y_train, y_val = train_test_split(
        X_final, y_final, test_size=0.1, stratify=y_final, random_state=42
    )

    # === 모델 구조 정의 (경량화 CNN) ===
    model = models.Sequential()
    model.add(layers.Conv2D(32, (3, 3), padding='same', input_shape=X_train[0].shape))
    model.add(layers.BatchNormalization())
    model.add(layers.Activation('relu'))
    model.add(layers.MaxPooling2D((2, 2)))
    model.add(layers.Dropout(0.25))

    model.add(layers.Conv2D(64, (3, 3), padding='same'))
    model.add(layers.BatchNormalization())
    model.add(layers.Activation('relu'))
    model.add(layers.MaxPooling2D((2, 2)))
    model.add(layers.Dropout(0.25))

    model.add(layers.Flatten())
    model.add(layers.Dense(64, activation='relu'))
    model.add(layers.Dropout(0.5))
    model.add(layers.Dense(3, activation='softmax'))  # 3 클래스 분류

    # === 컴파일 및 학습 ===
    model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])
    model.summary()
    model.fit(X_train, y_train, validation_data=(X_val, y_val), epochs=15, batch_size=64)

    # === 모델 저장 ===
    model.save(os.path.join(SAVE_PATH, "final_model"))
    model.save(os.path.join(SAVE_PATH, "final_model.h5"))
    print("[✅ 모델 저장 완료]")

# === 메인 함수 호출 (Windows 병렬 처리용) ===
if __name__ == '__main__':
    mp.freeze_support()
    main()
