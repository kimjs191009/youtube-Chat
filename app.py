import re
from collections import Counter

import pandas as pd
import streamlit as st
import plotly.express as px
import matplotlib.pyplot as plt

from googleapiclient.discovery import build
from wordcloud import WordCloud


st.set_page_config(page_title="YouTube 댓글 분석기", layout="wide")

st.title("📺 YouTube 댓글 분석기")


api_key = st.sidebar.text_input("YouTube API Key", type="password")

video_url = st.sidebar.text_input("YouTube URL")

max_comments = st.sidebar.slider("댓글 수", 20, 10000, 200, 20)


def extract_video_id(url):
    patterns = [
        r"v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})"
    ]

    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)

    return None


def get_comments(api_key, video_id, max_comments):
    youtube = build("youtube", "v3", developerKey=api_key)

    comments = []
    next_page_token = None

    while len(comments) < max_comments:

        request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=100,
            pageToken=next_page_token,
            textFormat="plainText"
        )

        res = request.execute()

        for item in res["items"]:
            s = item["snippet"]["topLevelComment"]["snippet"]

            comments.append({
                "comment": s["textDisplay"],
                "like": s["likeCount"],
                "time": s["publishedAt"]
            })

            if len(comments) >= max_comments:
                break

        next_page_token = res.get("nextPageToken")
        if not next_page_token:
            break

    return pd.DataFrame(comments)


def clean_text(text):
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"[^가-힣a-zA-Z0-9\s]", "", text)
    return text


def create_wordcloud(text):

    # ⭐ 핵심: Linux (Streamlit Cloud) 한글 폰트
    font_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"

    wc = WordCloud(
        font_path=font_path,
        width=1200,
        height=600,
        background_color="white"
    ).generate(text)

    return wc


if st.button("분석 시작"):

    if not api_key:
        st.error("API Key 필요")
        st.stop()

    video_id = extract_video_id(video_url)

    if not video_id:
        st.error("URL 오류")
        st.stop()

    df = get_comments(api_key, video_id, max_comments)

    if df.empty:
        st.warning("댓글 없음")
        st.stop()

    st.success(f"{len(df)}개 수집")

    # ---------------- WORDCLOUD ----------------
    st.subheader("워드클라우드")

    text = " ".join(df["comment"].astype(str))
    text = clean_text(text)

    wc = create_wordcloud(text)

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")

    st.pyplot(fig)
