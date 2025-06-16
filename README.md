# ECHO (Echo-based Alert & Response System)
  -청각약자를 위해 긴급소리(사이렌), 경고성소리(경적)을 실시간으로 감지하여 해당 소리에 대한 알람을 서보모터와 LED로 운전자에게 제공해주는 시스템이다.


  
#참여공모전: 2025 ESW Contest ECHO Projects - 자유공모



<사용 기자재>
1. Mike: SPH0645 , ICS43434
2. PC: Raspberry PI 5
3. Controller: Arduino Nano
4. Motor: SG90 Mini 5V
5. LED: [SMG] 5V USB Control 5050



<코드 구성>
1. 1. AI Model(CNN) - CNN모델 기반이며, 입력은 (64,60,1)형태의 Gammatonegram을 사용하였다.
    1) Model Training_Anaconda
    2) CNN Completed Model

2. Real-Time_Raspberry pi5_Inference - 실시간으로 소리를 분류
    - Classification_main5_timeframe_stereo

3. Serial to Arduino_Action - 분류된 소리를 Serial로 입력받아 서보모터와 LED패턴을 제어
    - Echo_Ver5_Anode_serial_raspberry
