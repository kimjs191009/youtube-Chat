import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
import plotly.express as px

st.set_page_config(page_title="YouTube Revenue Analyzer", layout="wide")

API_KEY = st.secrets["YOUTUBE_API_KEY"]

youtube = build(
    "youtube",
    "v3",
    developerKey=API_KEY
)

st.title("📺 YouTube 채널 수익 분석기")

channel_name = st.text_input(
    "유튜브 채널명 입력",
    placeholder="예: MrBeast"
)

def search_channel(name):
    request = youtube.search().list(
        q=name,
        part="snippet",
        type="channel",
        maxResults=1
    )
    response = request.execute()

    if len(response["items"]) == 0:
        return None

    return response["items"][0]["snippet"]["channelId"]

def get_channel_stats(channel_id):
    request = youtube.channels().list(
        part="statistics,snippet",
        id=channel_id
    )

    response = request.execute()

    if len(response["items"]) == 0:
        return None

    item = response["items"][0]

    return {
        "title": item["snippet"]["title"],
        "subs": int(item["statistics"].get("subscriberCount", 0)),
        "views": int(item["statistics"].get("viewCount", 0)),
        "videos": int(item["statistics"].get("videoCount", 0))
    }

def get_recent_videos(channel_id):
    request = youtube.search().list(
        part="snippet",
        channelId=channel_id,
        maxResults=20,
        order="date",
        type="video"
    )

    response = request.execute()

    video_ids = [
        item["id"]["videoId"]
        for item in response["items"]
    ]

    if not video_ids:
        return []

    stats_request = youtube.videos().list(
        part="statistics,snippet",
        id=",".join(video_ids)
    )

    stats_response = stats_request.execute()

    data = []

    for item in stats_response["items"]:
        data.append({
            "title": item["snippet"]["title"],
            "views": int(item["statistics"].get("viewCount", 0))
        })

    return data

if st.button("분석 시작"):

    with st.spinner("채널 분석 중..."):

        channel_id = search_channel(channel_name)

        if not channel_id:
            st.error("채널을 찾을 수 없습니다.")
            st.stop()

        stats = get_channel_stats(channel_id)

        st.subheader(stats["title"])

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "구독자",
            f"{stats['subs']:,}"
        )

        col2.metric(
            "총 조회수",
            f"{stats['views']:,}"
        )

        col3.metric(
            "영상 수",
            f"{stats['videos']:,}"
        )

        videos = get_recent_videos(channel_id)

        if videos:

            df = pd.DataFrame(videos)

            avg_views = int(df["views"].mean())

            # CPM 가정
            low_cpm = 1
            avg_cpm = 3
            high_cpm = 7

            monthly_views = avg_views * 4

            low_income = monthly_views / 1000 * low_cpm
            avg_income = monthly_views / 1000 * avg_cpm
            high_income = monthly_views / 1000 * high_cpm

            st.subheader("예상 월 수익")

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "보수적 추정",
                f"${low_income:,.0f}"
            )

            c2.metric(
                "평균 추정",
                f"${avg_income:,.0f}"
            )

            c3.metric(
                "높은 추정",
                f"${high_income:,.0f}"
            )

            st.subheader("예상 연 수익")

            st.success(
                f"${avg_income*12:,.0f}"
            )

            fig = px.bar(
                df,
                x="title",
                y="views",
                title="최근 영상 조회수"
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

            st.subheader("최근 영상 데이터")
            st.dataframe(df)

        else:
            st.warning("최근 영상을 찾을 수 없습니다.")
