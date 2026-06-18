import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import pandas as pd
import requests
import streamlit as st

# ──────────────────────────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────────────────────────
try:
    st.set_page_config(page_title="유튜브 채널 분석", page_icon="📊", layout="wide")
except Exception:
    pass

API_BASE = "https://www.googleapis.com/youtube/v3"


# ──────────────────────────────────────────────────────────────────
# 공용 유틸 함수
# ──────────────────────────────────────────────────────────────────
def format_count(n):
    """숫자를 한국식(만/억)으로 보기 좋게 표시"""
    if n is None:
        return "비공개"
    try:
        n = int(n)
    except (ValueError, TypeError):
        return "N/A"
    if n >= 100_000_000:
        return f"{n / 100_000_000:.2f}억"
    if n >= 10_000:
        return f"{n / 10_000:.1f}만"
    return f"{n:,}"


def parse_duration(duration_str):
    """ISO8601 길이(PT#H#M#S) → mm:ss 또는 h:mm:ss"""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_str or "")
    if not m:
        return "0:00"
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    if h > 0:
        return f"{h}:{mi:02d}:{s:02d}"
    return f"{mi}:{s:02d}"


def time_ago(dt):
    now = datetime.now(timezone.utc)
    delta = now - dt
    days = delta.days
    if days == 0:
        hours = delta.seconds // 3600
        if hours == 0:
            return f"{max(delta.seconds // 60, 1)}분 전"
        return f"{hours}시간 전"
    if days < 7:
        return f"{days}일 전"
    if days < 30:
        return f"{days // 7}주 전"
    if days < 365:
        return f"{days // 30}개월 전"
    return f"{days // 365}년 전"


def parse_channel_query(text):
    """입력값(URL/핸들/ID/이름)을 (타입, 값)으로 분류"""
    text = text.strip()
    if "youtube.com" in text or "youtu.be" in text:
        if not text.startswith("http"):
            text = "https://" + text
        path = urlparse(text).path.strip("/")
        parts = path.split("/") if path else []
        if parts:
            if parts[0] == "channel" and len(parts) > 1:
                return "id", parts[1]
            if parts[0].startswith("@"):
                return "handle", parts[0][1:]
            if parts[0] == "c" and len(parts) > 1:
                return "name", parts[1]
            if parts[0] == "user" and len(parts) > 1:
                return "username", parts[1]
            if parts[0].startswith("@") is False and len(parts) == 1:
                return "name", parts[0]
    if text.startswith("@"):
        return "handle", text[1:]
    if text.startswith("UC") and len(text) == 24:
        return "id", text
    return "name", text


class YoutubeAPIError(Exception):
    pass


def api_get(path, params):
    resp = requests.get(f"{API_BASE}/{path}", params=params, timeout=10)
    data = resp.json()
    if "error" in data:
        raise YoutubeAPIError(data["error"].get("message", "알 수 없는 API 오류가 발생했습니다."))
    return data


# ──────────────────────────────────────────────────────────────────
# API 호출 함수 (캐시 적용)
# ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def resolve_channel_id(api_key, query):
    qtype, qval = parse_channel_query(query)

    if qtype == "id":
        data = api_get("channels", {"part": "id", "id": qval, "key": api_key})
        if data.get("items"):
            return qval

    if qtype == "handle":
        data = api_get("channels", {"part": "id", "forHandle": qval, "key": api_key})
        if data.get("items"):
            return data["items"][0]["id"]

    if qtype == "username":
        data = api_get("channels", {"part": "id", "forUsername": qval, "key": api_key})
        if data.get("items"):
            return data["items"][0]["id"]

    # name 혹은 위에서 못 찾은 경우 → 핸들로 한번 더 시도
    data = api_get("channels", {"part": "id", "forHandle": qval, "key": api_key})
    if data.get("items"):
        return data["items"][0]["id"]

    # 최후의 수단: 검색 (쿼터 소모가 큼)
    data = api_get(
        "search",
        {"part": "snippet", "q": qval, "type": "channel", "maxResults": 1, "key": api_key},
    )
    if data.get("items"):
        return data["items"][0]["snippet"]["channelId"]

    return None


@st.cache_data(ttl=1800, show_spinner=False)
def get_channel_info(api_key, channel_id):
    data = api_get(
        "channels",
        {"part": "snippet,statistics,contentDetails", "id": channel_id, "key": api_key},
    )
    items = data.get("items")
    return items[0] if items else None


@st.cache_data(ttl=1800, show_spinner=False)
def get_recent_video_ids(api_key, uploads_playlist_id, max_results):
    video_ids, page_token = [], None
    while len(video_ids) < max_results:
        params = {
            "part": "contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": min(50, max_results - len(video_ids)),
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        data = api_get("playlistItems", params)
        for it in data.get("items", []):
            video_ids.append(it["contentDetails"]["videoId"])
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return video_ids


@st.cache_data(ttl=1800, show_spinner=False)
def get_videos_details(api_key, video_ids):
    rows = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        data = api_get(
            "videos",
            {"part": "snippet,statistics,contentDetails", "id": ",".join(chunk), "key": api_key},
        )
        for it in data.get("items", []):
            snippet, stats = it["snippet"], it.get("statistics", {})
            rows.append({
                "video_id": it["id"],
                "title": snippet.get("title"),
                "published_at": snippet.get("publishedAt"),
                "thumbnail": (snippet.get("thumbnails", {}).get("medium")
                              or snippet.get("thumbnails", {}).get("default") or {}).get("url"),
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats["likeCount"]) if "likeCount" in stats else None,
                "comments": int(stats["commentCount"]) if "commentCount" in stats else None,
                "duration": parse_duration(it.get("contentDetails", {}).get("duration")),
            })
    return rows


# ──────────────────────────────────────────────────────────────────
# 성장률 · 채널 점수 계산
# ──────────────────────────────────────────────────────────────────
def calc_growth(df):
    """최근 절반 vs 그 이전 절반 영상의 평균 조회수를 비교해 성장률 추정"""
    n = len(df)
    if n < 4:
        return None
    half = max(2, n // 2)
    recent = df.iloc[:half]
    older = df.iloc[half: half * 2]
    if older.empty or older["views"].mean() == 0:
        return None
    avg_recent, avg_older = recent["views"].mean(), older["views"].mean()
    growth_rate = (avg_recent - avg_older) / avg_older * 100
    return {
        "avg_recent": avg_recent, "avg_older": avg_older,
        "growth_rate": growth_rate, "recent_n": half, "older_n": len(older),
    }


def calc_monthly_uploads(df):
    if len(df) < 2:
        return float(len(df))
    dates = pd.to_datetime(df["published_at"])
    span_days = (dates.max() - dates.min()).days
    if span_days <= 0:
        return float(len(df))
    return len(df) / (span_days / 30)


def calc_engagement_rate(df):
    valid = df.dropna(subset=["likes", "comments"])
    valid = valid[valid["views"] > 0]
    if valid.empty:
        return None
    rates = (valid["likes"] + valid["comments"]) / valid["views"]
    return rates.mean()


def score_by_tier(value, tiers):
    for threshold, score in tiers:
        if value >= threshold:
            return score
    return tiers[-1][1]


SUB_TIERS = [(1_000_000, 20), (100_000, 16), (10_000, 12), (1_000, 8), (100, 4), (0, 2)]
VIEW_TIERS = [(1_000_000, 20), (100_000, 16), (10_000, 12), (1_000, 8), (100, 4), (0, 2)]
ENGAGE_TIERS = [(0.10, 20), (0.05, 16), (0.02, 12), (0.01, 8), (0.005, 4), (0, 2)]
UPLOAD_TIERS = [(8, 15), (4, 12), (2, 9), (1, 6), (0.1, 3), (0, 0)]
GROWTH_TIERS = [(50, 25), (20, 20), (0, 15), (-20, 10), (-50, 5), (-1000, 0)]


def calc_channel_score(channel_info, df):
    stats = channel_info.get("statistics", {})
    hidden_subs = stats.get("hiddenSubscriberCount", False)
    subs = None if hidden_subs else int(stats.get("subscriberCount", 0))

    avg_views = df["views"].mean() if not df.empty else 0
    engagement = calc_engagement_rate(df)
    monthly_uploads = calc_monthly_uploads(df)
    growth = calc_growth(df)

    sub_score = 10 if subs is None else score_by_tier(subs, SUB_TIERS)
    view_score = score_by_tier(avg_views, VIEW_TIERS)
    engage_score = 10 if engagement is None else score_by_tier(engagement, ENGAGE_TIERS)
    upload_score = score_by_tier(monthly_uploads, UPLOAD_TIERS)
    growth_score = 12 if growth is None else score_by_tier(growth["growth_rate"], GROWTH_TIERS)

    total = sub_score + view_score + engage_score + upload_score + growth_score

    if total >= 90:
        grade = "S"
    elif total >= 75:
        grade = "A"
    elif total >= 60:
        grade = "B"
    elif total >= 40:
        grade = "C"
    else:
        grade = "D"

    breakdown = [
        ("구독자 규모", sub_score, 20),
        ("평균 조회수", view_score, 20),
        ("참여율(좋아요+댓글/조회수)", engage_score, 20),
        ("업로드 활성도", upload_score, 15),
        ("성장 추세", growth_score, 25),
    ]
    return total, grade, breakdown, {
        "subs": subs, "avg_views": avg_views, "engagement": engagement,
        "monthly_uploads": monthly_uploads, "growth": growth,
    }


# ──────────────────────────────────────────────────────────────────
# 화면 구성
# ──────────────────────────────────────────────────────────────────
def get_api_key():
    if "YOUTUBE_API_KEY" in st.secrets:
        return st.secrets["YOUTUBE_API_KEY"]
    if st.session_state.get("yt_api_key"):
        return st.session_state["yt_api_key"]
    with st.sidebar:
        st.markdown("### 🔑 YouTube API 키")
        key = st.text_input("YouTube Data API v3 키", type="password", key="yt_api_key_input")
        if key:
            st.session_state["yt_api_key"] = key
            return key
    return None


def main():
    st.title("📊 유튜브 채널 분석")
    st.caption("채널 URL/핸들/ID를 입력하면 최근 업로드, 성장률, 채널 점수를 분석해드려요.")

    api_key = get_api_key()
    if not api_key:
        st.info("좌측 사이드바에 YouTube Data API v3 키를 입력해주세요.")
        st.stop()

    with st.sidebar:
        max_results = st.slider("분석할 최근 영상 수", min_value=10, max_value=50, value=20, step=5)

    col1, col2 = st.columns([4, 1])
    with col1:
        query = st.text_input(
            "채널 URL / @핸들 / 채널ID / 채널명",
            placeholder="예: https://www.youtube.com/@채널이름  또는  @채널이름",
        )
    with col2:
        st.write("")
        st.write("")
        run = st.button("분석하기", use_container_width=True, type="primary")

    if not (run and query):
        return

    try:
        with st.spinner("채널 정보를 찾는 중..."):
            channel_id = resolve_channel_id(api_key, query)
        if not channel_id:
            st.error("채널을 찾을 수 없습니다. URL/핸들/채널명을 다시 확인해주세요.")
            return

        with st.spinner("채널 정보를 불러오는 중..."):
            channel_info = get_channel_info(api_key, channel_id)
        if not channel_info:
            st.error("채널 정보를 불러오지 못했습니다.")
            return

        uploads_playlist = (
            channel_info.get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("uploads")
        )
        if not uploads_playlist:
            st.error("이 채널의 업로드 영상 목록을 찾을 수 없습니다.")
            return

        with st.spinner("최근 업로드 영상을 불러오는 중..."):
            video_ids = get_recent_video_ids(api_key, uploads_playlist, max_results)
            video_rows = get_videos_details(api_key, video_ids)

    except YoutubeAPIError as e:
        st.error(f"YouTube API 오류: {e}")
        return
    except requests.exceptions.RequestException as e:
        st.error(f"네트워크 오류: {e}")
        return

    if not video_rows:
        st.warning("업로드된 영상을 찾을 수 없습니다.")
        return

    df = pd.DataFrame(video_rows)
    df["published_at_dt"] = pd.to_datetime(df["published_at"])
    df = df.sort_values("published_at_dt", ascending=False).reset_index(drop=True)

    snippet = channel_info.get("snippet", {})
    stats = channel_info.get("statistics", {})
    created_at = datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00"))
    channel_age_days = (datetime.now(timezone.utc) - created_at).days

    tab1, tab2, tab3, tab4 = st.tabs(["채널 개요", "최근 업로드", "성장률 분석", "채널 점수"])

    # ── 탭1: 채널 개요 ──────────────────────────────────────────
    with tab1:
        c1, c2 = st.columns([1, 4])
        with c1:
            thumb = snippet.get("thumbnails", {}).get("high", {}).get("url")
            if thumb:
                st.image(thumb, width=120)
        with c2:
            st.subheader(snippet.get("title", ""))
            st.caption(snippet.get("description", "")[:200])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("구독자", format_count(stats.get("subscriberCount")) if not stats.get("hiddenSubscriberCount") else "비공개")
        m2.metric("총 조회수", format_count(stats.get("viewCount")))
        m3.metric("총 영상 수", format_count(stats.get("videoCount")))
        m4.metric("채널 운영 기간", f"{channel_age_days // 365}년 {channel_age_days % 365 // 30}개월")

        avg_monthly_sub_growth = None
        if not stats.get("hiddenSubscriberCount") and channel_age_days > 0:
            avg_monthly_sub_growth = int(stats.get("subscriberCount", 0)) / (channel_age_days / 30)
        if avg_monthly_sub_growth is not None:
            st.caption(f"📈 채널 개설 이후 평균 구독자 증가: 월 약 {format_count(round(avg_monthly_sub_growth))}명 (추정치)")

    # ── 탭2: 최근 업로드 ────────────────────────────────────────
    with tab2:
        st.subheader(f"최근 업로드 영상 {len(df)}개")
        display_df = df.copy()
        display_df["업로드"] = display_df["published_at_dt"].apply(time_ago)
        display_df["조회수"] = display_df["views"].apply(format_count)
        display_df["좋아요"] = display_df["likes"].apply(format_count)
        display_df["댓글"] = display_df["comments"].apply(format_count)
        display_df["링크"] = "https://www.youtube.com/watch?v=" + display_df["video_id"]

        st.dataframe(
            display_df[["thumbnail", "title", "업로드", "duration", "조회수", "좋아요", "댓글", "링크"]],
            column_config={
                "thumbnail": st.column_config.ImageColumn("썸네일"),
                "title": st.column_config.TextColumn("제목", width="large"),
                "duration": st.column_config.TextColumn("길이"),
                "링크": st.column_config.LinkColumn("바로가기", display_text="보기"),
            },
            hide_index=True,
            use_container_width=True,
        )

    # ── 탭3: 성장률 분석 ────────────────────────────────────────
    with tab3:
        st.subheader("최근 영상 조회수 추이")
        chart_df = df.sort_values("published_at_dt")[["published_at_dt", "views"]].set_index("published_at_dt")
        st.line_chart(chart_df)

        growth = calc_growth(df)
        if growth:
            delta_label = f"{growth['growth_rate']:+.1f}%"
            st.metric(
                f"최근 {growth['recent_n']}개 vs 이전 {growth['older_n']}개 평균 조회수",
                format_count(round(growth["avg_recent"])),
                delta=delta_label,
            )
            if growth["growth_rate"] > 0:
                st.success(f"📈 최근 영상들의 평균 조회수가 이전보다 {growth['growth_rate']:.1f}% 높습니다. 상승 추세입니다.")
            else:
                st.warning(f"📉 최근 영상들의 평균 조회수가 이전보다 {abs(growth['growth_rate']):.1f}% 낮습니다. 하락 추세입니다.")
        else:
            st.info("성장률을 계산하기에 영상 데이터가 충분하지 않습니다. (최소 4개 이상 필요)")

        monthly_uploads = calc_monthly_uploads(df)
        st.metric("월평균 업로드 빈도(분석 영상 기준)", f"{monthly_uploads:.1f}개/월")

    # ── 탭4: 채널 점수 ──────────────────────────────────────────
    with tab4:
        total, grade, breakdown, info = calc_channel_score(channel_info, df)

        c1, c2 = st.columns([1, 2])
        with c1:
            st.metric("종합 채널 점수", f"{total:.0f} / 100", delta=f"{grade}등급")
        with c2:
            st.caption(
                "구독자 규모(20) · 평균 조회수(20) · 참여율(20) · 업로드 활성도(15) · 성장 추세(25)"
                " 5개 항목을 합산한 100점 만점 점수입니다."
            )

        st.divider()
        for label, score, max_score in breakdown:
            st.write(f"**{label}**  —  {score} / {max_score}점")
            st.progress(score / max_score)

        st.divider()
        st.caption(
            "※ 이 점수는 YouTube Data API로 확인 가능한 공개 지표(구독자/조회수/좋아요/댓글/업로드 주기)를 "
            "기반으로 한 추정 점수이며, 채널의 실제 가치나 영향력을 절대적으로 평가하는 지표는 아닙니다."
        )


main()
