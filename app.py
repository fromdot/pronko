import streamlit as st
import pandas as pd
import difflib
import re
import Levenshtein
from openai import OpenAI
from streamlit_mic_recorder import mic_recorder
import random

# --- 0. 페이지 설정 ---
st.set_page_config(layout="wide", page_title="Pronko - AI Pronunciation Analyzer")

# --- 1. 다국어 텍스트 및 상태 관리 ---
def initialize_state():
    """세션 상태를 초기화합니다."""
    if 'lang' not in st.session_state:
        st.session_state.lang = 'ko'
    if 'prompt' not in st.session_state:
        st.session_state.prompt = ""
    if 'guide_audio' not in st.session_state:
        st.session_state.guide_audio = None

TEXTS = {
    "ko": {
        "title": "AI 한국어 발음 분석기", "lang_select": "언어 선택", "header": "발음 연습", 
        "prompt_source": "연습 문장 선택", "source_random": "랜덤 문장", "source_gpt": "AI 생성",
        "new_sentence_button": "새로운 랜덤 문장",
        "start_prompt": "🎤 녹음 시작", "stop_prompt": "⏹️ 녹음 중지", "result_header": "음성 분석 결과", 
        "my_audio": "내 녹음 다시 듣기", "accuracy": "발음 정확도", "compare_header": "상세 비교 분석", 
        "compare_std": "목표 발음", "compare_pred": "내 발음 인식 결과 (AI)", 
        "error_api_key": "OpenAI API 키를 .streamlit/secrets.toml에 설정해주세요.",
        "spinner_tts": "가이드 음성을 생성 중입니다...", "spinner_stt": "AI가 당신의 발음을 분석 중입니다...",
    },
    "en": {
        "title": "AI Korean Pronunciation Analyzer", "lang_select": "Select Language", "header": "Pronunciation Practice", 
        "prompt_source": "Choose a practice sentence", "source_random": "Random Sentence", "source_gpt": "AI Generated",
        "new_sentence_button": "New Random Sentence",
        "start_prompt": "▶️ Start Recording", "stop_prompt": "⏹️ Stop Recording", "result_header": "Voice Analysis Result", 
        "my_audio": "Listen to My Recording", "accuracy": "Pronunciation Accuracy", "compare_header": "Detailed Comparison",
        "compare_std": "Target Pronunciation", "compare_pred": "My Pronunciation (AI Recognized)", 
        "error_api_key": "Please set up your OpenAI API key in .streamlit/secrets.toml",
        "spinner_tts": "Generating guide audio...", "spinner_stt": "AI is analyzing your pronunciation...",
    }
}

# --- 2. 핵심 로직 함수들 ---

@st.cache_resource
def get_openai_client():
    """OpenAI 클라이언트 객체를 생성하고 캐시합니다."""
    try:
        return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    except (KeyError, FileNotFoundError):
        st.error(TEXTS[st.session_state.get('lang', 'ko')]["error_api_key"])
        st.stop()

@st.cache_data
def get_practice_sentences():
    """미리 정의된 연습 문장 목록을 반환합니다."""
    return [
        "나는 집 내부 공사를 끝냈다.", "아침에 아무것도 먹지 않는 사람들이 많습니다.",
        "너는 클래식 음악 듣는 걸 좋아하지, 그렇지?", "생선을 먹던 고양이가 강아지한테 쫓겼다.",
    ]

def preprocess_text(text: str) -> str:
    """CER 계산을 위해 텍스트에서 공백과 특수문자를 제거합니다."""
    text = text.lower().strip()
    return re.sub(r"[^a-z0-9가-힣]", "", text)

def calculate_cer(prediction: str, standard: str) -> float:
    """두 텍스트의 글자 오류율(CER)을 계산합니다."""
    pred_clean = preprocess_text(prediction)
    std_clean = preprocess_text(standard)
    distance = Levenshtein.distance(pred_clean, std_clean)
    std_len = len(std_clean)
    return round(distance / std_len, 4) if std_len > 0 else 0.0

# ⭐️ 캐시 제거: 녹음할 때마다 항상 새로 분석해야 함
def analyze_with_whisper(_client, _audio_bytes):
    """Whisper API를 호출하여 음성을 텍스트로 변환합니다."""
    with st.spinner(TEXTS[st.session_state.lang]['spinner_stt']):
        try:
            audio_file = ("audio.wav", _audio_bytes, "audio/wav")
            transcription = _client.audio.transcriptions.create(model="whisper-1", file=audio_file, response_format="text")
            return transcription
        except Exception as e:
            st.error(f"{TEXTS[st.session_state.lang]['error_api_call']} {e}")
            return None

# @st.cache_data
def generate_tts(_client, _text):
    """OpenAI TTS API를 호출하여 가이드 음성을 생성합니다."""
    with st.spinner(TEXTS[st.session_state.lang]['spinner_tts']):
        try:
            response = _client.audio.speech.create(model="tts-1", voice="nova", input=_text)
            return response.content
        except Exception as e:
            st.error(f"{TEXTS[st.session_state.lang]['error_api_call']} {e}")
            return None

def render_diff_comparison(std_text: str, pred_text: str, T):
    """
    [최종 시각화 함수]
    목표 발음은 그대로, 예측 발음에서만 맞고 틀린 부분을 색상으로 표시합니다.
    """
    matcher = difflib.SequenceMatcher(None, std_text, pred_text)
    
    styled_prediction = ""
    # 모던한 색상 팔레트
    match_color = "#198754"  # 일치: 선명한 초록색 (Bootstrap Success)
    error_color = "#dc3545"  # 불일치: 선명한 빨간색 (Bootstrap Danger)
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            styled_prediction += f'<span style="color: {match_color}; font-weight: 500;">{pred_text[j1:j2]}</span>'
        else:
            styled_prediction += f'<span style="color: {error_color}; font-weight: 700; text-decoration: underline; text-decoration-style: wavy;">{pred_text[j1:j2]}</span>'

    # UI 렌더링
    style = "font-size: 1.2rem; padding: 15px; border: 1px solid #dee2e6; border-radius: 8px; line-height: 2.0;"
    
    st.markdown(f"**{T['compare_std']}**")
    st.markdown(f'<div style="{style}">{std_text}</div>', unsafe_allow_html=True)
    
    st.markdown(f"**{T['compare_pred']}**")
    st.markdown(f'<div style="{style}">{styled_prediction}</div>', unsafe_allow_html=True)

# --- 3. 메인 애플리케이션 실행 ---
# --- 3. 메인 애플리케이션 실행 ---

# 1. 초기화
initialize_state()
client = get_openai_client()

# 2. 사이드바 (언어 선택)
with st.sidebar:
    st.title("Settings")
    # 언어가 변경되면, prompt와 audio를 초기화하고 스크립트를 재실행
    if st.radio("Language", ["ko", "en"], format_func=lambda x: "한국어" if x == "ko" else "English", key="lang_selector") != st.session_state.lang:
        st.session_state.lang = "en" if st.session_state.lang == "ko" else "ko"
        st.session_state.prompt = ""
        st.session_state.guide_audio = None
        st.rerun()

T = TEXTS[st.session_state.lang]

# 3. 메인 페이지 레이아웃
st.title(T["title"])
st.header(T["header"])

# 4. 문장 선택 UI
source_option = st.radio(
    T["prompt_source"],
    options=["random", "gpt"],
    format_func=lambda x: T["source_random"] if x == "random" else T["source_gpt"],
    horizontal=True,
    key="source_option_radio"
)

if source_option == "random":
    if st.button(T["new_sentence_button"], key="new_random_sentence_button"):
        st.session_state.prompt = random.choice(get_practice_sentences())
        st.session_state.guide_audio = None # 캐시 무효화
        st.rerun()
else: # GPT
    with st.form(key="gpt_form"):
        topic = st.text_input(TEXTS[st.session_state.lang]["gpt_placeholder"], key="gpt_topic_input")
        submitted = st.form_submit_button(TEXTS[st.session_state.lang]["gpt_prompt_button"])
        if submitted and topic:
            new_prompt = generate_sentence_with_gpt(client, topic, st.session_state.lang)
            if new_prompt:
                st.session_state.prompt = new_prompt
                st.session_state.guide_audio = None
                st.rerun()

# 5. 현재 연습 문장 및 가이드 오디오 표시
# 최초 실행 시 또는 문장이 없을 때 초기 문장 설정
if not st.session_state.prompt:
    st.session_state.prompt = get_practice_sentences()[0]
    st.session_state.guide_audio = None # 오디오도 함께 초기화

# TTS 오디오 생성 및 캐싱 로직
if st.session_state.guide_audio is None:
    audio_content = generate_tts(client, st.session_state.prompt)
    st.session_state.guide_audio = audio_content
    
st.subheader(st.session_state.prompt, divider='rainbow')
if st.session_state.guide_audio:
    st.audio(st.session_state.guide_audio, format="audio/mp3")

# 6. 마이크 녹음 및 분석
audio_info = mic_recorder(
    start_prompt=T["start_prompt"],
    stop_prompt=T["stop_prompt"],
    just_once=True,
    key='mic_recorder_widget'
)

if audio_info and audio_info['bytes']:
    st.header(T["result_header"], divider='rainbow')
    
    col_listen, col_score = st.columns([1, 2])
    
    with col_listen:
        st.markdown(f"**{T['my_audio']}**")
        st.audio(audio_info['bytes'])
        
    predicted_text = analyze_with_whisper(client, audio_info['bytes'])
    
    if predicted_text:
        cer_score = calculate_cer(predicted_text, st.session_state.prompt)
        accuracy = max(0, (1 - cer_score)) * 100
        
        with col_score:
            st.metric(label=f"**{T['accuracy']}**", value=f"{accuracy:.1f} %",
                      help="글자 오류율(CER)을 기반으로 계산된 정확도입니다.")

        # 최종 시각화 함수 호출
        render_diff_comparison(st.session_state.prompt, predicted_text, T)