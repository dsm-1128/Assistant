"""Legacy Streamlit 入口。

生产部署使用 Vue 3 + FastAPI；此文件保留原项目的 Streamlit 使用方式，
但生成与向量化同样调用新的在线 OpenAI-compatible API。
"""

from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
from pydantic import ValidationError

from travel_assistant.config import Settings
from travel_assistant.model import (
    OnlineChatModel,
    OnlineEmbeddingClient,
    OnlineServiceError,
)
from travel_assistant.planner import GuideGenerationError, TravelPlanner
from travel_assistant.rag import (
    SUPPORTED_EXTENSIONS,
    DocumentLoadError,
    EmbeddingModelError,
    KnowledgeDocument,
    TravelKnowledgeBase,
)
from travel_assistant.schemas import Evidence, TravelGuide, TravelRequest

st.set_page_config(page_title="旅行智能助手（Legacy）", page_icon="🧭", layout="wide")


@st.cache_resource
def get_settings() -> Settings:
    return Settings.from_env()


@st.cache_resource
def get_embedding_client() -> OnlineEmbeddingClient:
    return OnlineEmbeddingClient(get_settings())


@st.cache_resource
def get_knowledge_base() -> TravelKnowledgeBase:
    return TravelKnowledgeBase(get_settings(), get_embedding_client())


@st.cache_resource
def get_model() -> OnlineChatModel:
    return OnlineChatModel(get_settings())


@st.cache_resource
def get_planner() -> TravelPlanner:
    return TravelPlanner(get_knowledge_base(), get_model())


def render_guide(guide: TravelGuide, evidence: list[Evidence]) -> None:
    st.header(guide.title)
    if guide.insufficient_evidence:
        st.warning("没有检索到该目的地的知识库资料，本攻略主要来自在线模型的通用规划能力。")
    st.write(guide.overview)
    with st.expander("规划思路", expanded=True):
        for item in guide.planning_rationale:
            st.markdown(f"- {item}")

    for day_plan in guide.days:
        st.subheader(f"第 {day_plan.day} 天 · {day_plan.date} · {day_plan.theme}")
        for activity in day_plan.activities:
            citation_text = " ".join(f"[{item}]" for item in activity.citations)
            st.markdown(
                f"**{activity.period}｜{activity.activity}**  {citation_text}\n\n"
                f"地点：{activity.location or '待定'}　时长：{activity.duration or '按实际安排'}　"
                f"交通：{activity.transport or '步行或公共交通'}　"
                f"估算：{activity.estimated_cost:.0f}"
            )
        if day_plan.meals:
            st.caption("餐饮建议：" + "；".join(day_plan.meals))
        if day_plan.notes:
            st.caption("当日提醒：" + "；".join(day_plan.notes))

    left, right = st.columns(2)
    with left:
        st.subheader("交通建议")
        for item in guide.transportation_advice:
            st.markdown(f"- {item}")
        st.subheader("餐饮与住宿")
        for item in guide.food_and_stay_advice:
            st.markdown(f"- {item}")
    with right:
        st.subheader("预算估算")
        st.dataframe(
            [item.model_dump() for item in guide.budget_items],
            use_container_width=True,
            hide_index=True,
        )
        st.metric("估算总额", f"{guide.budget_total:,.0f}")

    st.subheader("行前准备")
    for item in guide.preparation:
        st.markdown(f"- {item}")
    st.subheader("风险与避坑")
    for item in guide.warnings:
        st.warning(item)

    evidence_by_id = {item.id: item for item in evidence}
    referenced_ids = list(guide.citations)
    for day_plan in guide.days:
        for activity in day_plan.activities:
            referenced_ids.extend(activity.citations)
    referenced = [
        evidence_by_id[item]
        for item in dict.fromkeys(referenced_ids)
        if item in evidence_by_id
    ]
    if referenced:
        with st.expander("资料来源", expanded=True):
            for item in referenced:
                st.markdown(
                    f"**[{item.id}] {item.source}** · {item.topic} · 更新：{item.updated_at}\n\n"
                    f"{item.content[:400]}{'…' if len(item.content) > 400 else ''}"
                )
    st.caption(
        "预算、交通耗时及行程安排均为规划建议；营业时间、票价、天气和班次请在出发前通过官方渠道确认。"
    )


def guide_tab() -> None:
    st.subheader("生成自定义目的地攻略")
    with st.form("travel_request"):
        col1, col2 = st.columns(2)
        with col1:
            origin = st.text_input("出发地", placeholder="例如：上海")
            destination = st.text_input("目的地", placeholder="例如：成都")
            start_date = st.date_input(
                "出发日期", value=date.today() + timedelta(days=14)
            )
            end_date = st.date_input(
                "返回日期", value=date.today() + timedelta(days=17)
            )
            adults = st.number_input("成人数", min_value=0, value=1, step=1)
            children = st.number_input("儿童数", min_value=0, value=0, step=1)
        with col2:
            budget = st.number_input(
                "总预算", min_value=0.0, value=5000.0, step=100.0
            )
            currency = st.selectbox("币种", ["CNY", "USD", "EUR", "JPY", "HKD"])
            interests_text = st.text_input("兴趣（用逗号分隔）", value="美食, 人文")
            pace = st.select_slider(
                "旅行节奏", options=["轻松", "适中", "紧凑"], value="适中"
            )
            accommodation = st.text_input("住宿偏好", value="交通方便、安静")
            dietary = st.text_input("饮食禁忌", value="无")
        must_visit_text = st.text_input("必去地点（用逗号分隔）")
        additional = st.text_area("其他要求")
        submitted = st.form_submit_button("生成攻略", type="primary")

    if not submitted:
        return

    def split_values(value: str) -> list[str]:
        return [
            item.strip()
            for item in value.replace("，", ",").split(",")
            if item.strip()
        ]

    try:
        request = TravelRequest(
            origin=origin,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            adults=int(adults),
            children=int(children),
            budget=budget,
            currency=currency,
            interests=split_values(interests_text),
            pace=pace,
            accommodation=accommodation,
            dietary_restrictions=dietary,
            must_visit=split_values(must_visit_text),
            additional_requirements=additional,
        )
        with st.spinner("正在检索资料并调用在线模型生成攻略……"):
            planner = get_planner()
            guide = planner.create_guide(request)
        render_guide(guide, planner.last_evidence)
    except ValidationError as exc:
        st.error(f"旅行条件不完整：{exc}")
    except (
        EmbeddingModelError,
        OnlineServiceError,
        GuideGenerationError,
        RuntimeError,
        OSError,
        ValueError,
    ) as exc:
        st.error(f"生成失败：{exc}")


def knowledge_tab() -> None:
    st.subheader("导入目的地知识")
    destination = st.text_input("资料对应目的地", key="kb_destination")
    topic = st.text_input("资料主题", value="综合", key="kb_topic")
    updated_at = st.date_input("资料更新时间", value=date.today(), key="kb_updated")
    uploads = st.file_uploader(
        "上传 TXT、Markdown 或文本型 PDF",
        type=[suffix.lstrip(".") for suffix in sorted(SUPPORTED_EXTENSIONS)],
        accept_multiple_files=True,
    )
    if not st.button("写入知识库", type="primary"):
        return
    if not destination.strip() or not uploads:
        st.error("请填写目的地并至少上传一个文件。")
        return
    try:
        with tempfile.TemporaryDirectory(prefix="travel-kb-") as temp_dir:
            documents = []
            for upload in uploads:
                safe_name = Path(upload.name).name
                path = Path(temp_dir) / safe_name
                path.write_bytes(upload.getbuffer())
                documents.append(
                    KnowledgeDocument(path, destination, topic, updated_at)
                )
            with st.spinner("正在解析资料并通过在线 API 生成向量……"):
                report = get_knowledge_base().ingest(documents)
        st.success(f"入库完成：{report.files} 个文件，{report.chunks} 个片段。")
    except (
        DocumentLoadError,
        EmbeddingModelError,
        OnlineServiceError,
        RuntimeError,
        OSError,
        ValueError,
    ) as exc:
        st.error(f"入库失败：{exc}")


def status_tab() -> None:
    st.subheader("运行状态")
    settings = get_settings()
    model_status = get_model().status()
    kb_status = get_knowledge_base().status()
    st.json(
        {
            "Chat API 配置完整": model_status.configured,
            "Chat 模型": model_status.model,
            "Chat Base URL": model_status.base_url,
            "Embedding API 配置完整": settings.embedding_configured,
            "Embedding 模型": settings.embedding_model,
            "Embedding 维度": settings.embedding_dimension,
            "知识库 Collection": kb_status.collection_name,
            "知识库目录": kb_status.path,
            "知识片段数": kb_status.chunks,
            "Collection 兼容": kb_status.compatible,
            "Collection 状态": kb_status.compatibility_message,
        }
    )


st.title("🧭 旅行智能助手")
st.warning(
    "当前为保留的 Legacy Streamlit 界面。生产部署请使用 Vue 3 + FastAPI；"
    "此界面与新服务共用在线模型配置和 ChromaDB。"
)
st.caption("在线 Chat + 在线 Embedding + ChromaDB RAG，为目的地生成个性化中文攻略")
tab_guide, tab_knowledge, tab_status = st.tabs(
    ["生成攻略", "知识库管理", "运行状态"]
)
with tab_guide:
    guide_tab()
with tab_knowledge:
    knowledge_tab()
with tab_status:
    status_tab()
