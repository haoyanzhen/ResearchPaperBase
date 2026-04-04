from openai import OpenAI, AsyncOpenAI
from typing import List, TypedDict, Optional
from langgraph.graph import StateGraph, END

import requests
import json

class GraphState(TypedDict):
    model: str                  # 使用模型
    # provider: str               # 提供商 ('openai', 'ollama', 'custom')
    api_key: str                # 密钥
    base_url: str               # API地址
    topic: str                  # 用户初始课题
    history: List[dict]
    queries: List[str]          # 生成的搜索词列表
    raw_results: List[dict]     # 检索到的原始数据汇总
    filtered_papers: List[dict] # 评分通过的论文
    processed_count: int        # 已处理篇数
    final_db_update: bool       # 数据库更新状态

'''
def call_llm(
    prompt: str, 
    input_text: str, 
    model: str = "gpt-4o", 
    provider: str = "openai",
    base_url: str = None,
    api_key: str = "",
):
    """
    通用 LLM 调用接口
    :param prompt: 系统提示词/指令
    :param input_text: 用户的输入文本
    :param model: 模型名称
    :param provider: 提供商 ('openai', 'ollama', 'custom')
    :param api_key: 密钥 (本地 Ollama 通常不需要)
    :param base_url: 自定义 API 地址
    """
    
    full_user_content = f"{input_text}"
    
    if provider == "ollama":
        url = base_url or "http://localhost:11434/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
    else:
        url = base_url or "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": full_user_content}
        ],
        "temperature": 0.3  # 学术场景建议低随机性
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        response.raise_for_status()
        result = response.json()
        
        # 统一提取文本内容
        return result['choices'][0]['message']['content']
    
    except Exception as e:
        return f"LLM 调用失败 [{provider}]: {str(e)}"
'''

def call_llm_sdk(prompt, input_text, history=None, model="deepseek-chat", api_key="", base_url="https://api.deepseek.com"):
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    message = [{"role": "system", "content": prompt}]
    if history:
        message.extend(history)
    message.append({"role": "user", "content": input_text})

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=message,
            temperature=0.3
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"调用失败: {e}"

def my_node(state: GraphState):
    # 1. 读取状态
    topic = state["topic"]
    # 2. 执行逻辑 (如调用工具或处理数据)
    print(f"正在处理课题: {topic}")
    # 3. 返回更新 (增量更新 State)
    return {"processed_count": state["processed_count"] + 1}

def generate_queries_func(state: GraphState):
    model = state["model"]
    api_key = state["api_key"]
    base_url = state["base_url"]

    topic = state["topic"]
    
    print(f"正在处理课题: {topic}")
    queries = call_llm_sdk(
        model = model,
        api_key = api_key,
        base_url = base_url,
        prompt="""Role: 你是一位资深的学术情报专家，精通各个学科的索引逻辑与布尔检索语法。
Task: 请针对用户提供的研究课题，生成一组具备“高覆盖率”和“高查全率”的检索词列表。
Dimension: 请从以下四个维度进行发散：
   - 核心概念及其变体：包含学术全称、缩写、常用别名。
   - 技术路径与方法：实现该课题的具体工艺、算法或理论模型。
   - 关联属性与评价指标：课题关注的核心性能（如稳定性、效率、鲁棒性）。
   - 上位词与下位词：所属的更广领域和具体的细分分支。
Output Format:
请返回一个 JSON 格式，包含：
   - keywords: 按维度分类的关键词列表。
   - boolean_queries: 针对不同数据库（arXiv、OpenAlex、Semantic Schola、astrophysics data system）优化的布尔表达式字符串。
""", 
        input_text="User topic: %s" % topic, 
    )

    history = state["history"] + [
        {"role": "user", "content": f"User topic: {topic}"},
        {"role": "assistant", "content": queries}
    ]

    return {"queries": queries, 
            "history": history,
            "processed_count": state["processed_count"] + 1}

def search_and_aggregate_func(state: GraphState):
    queries = state["queries"]
    for paperdb, queries_list in queries["boolean_queries"].items():
        if paperdb == "arXiv":
            parser = ...
        pass

        for query in queries_list:
            paper_info = parser.parse()
            pass

    return {"raw_results": paper_info,
            "processed_count": state["processed_count"] + 1} 

def score_and_filter_func(state: GraphState):
    model = state["model"]
    api_key = state["api_key"]
    base_url = state["base_url"]

    topic = state["topic"]
    
    raw_results = state["raw_results"]
    for item in raw_results:
        title = item["title"]
        abstract = item["abstract"]
        periodical = item["periodical"]
        authors = item["authors"]

    scored_paper_list = []
    #TODO: 如何异步执行该函数或异步执行client.chat.completions.create
    score = call_llm_sdk(
        model = model,
        api_key = api_key,
        base_url = base_url,
        prompt="""
Role: 你是一位严谨的学术预审编辑，擅长评估学术论文的潜在研究价值与工程落地可能性。
Task: 根据提供的论文元数据（标题、摘要、期刊、作者）与目标研究课题，从“参考价值”和“技术借鉴价值”两个维度进行深度打分。
Evaluation Criteria:
   1. 参考价值 (Reference score) [0-5分，最低0分]:
      - +2分：研究内容与目标课题有较大相关性
      - +2分：在实际数据的测试结果非常良好
      - +1分：来自顶级期刊/会议
      - -1分：内容泛泛而谈，没有突出性成果或创新
      - -2分：东拉西扯，不深化研究问题，不提出新的设想
   2. 技术借鉴价值 (Technical score) [0-5分，最低0分]:
      - +2分：技术能够直接用于指定的方向
      - +1分：论证严密，测试全面，能够论证技术或理论的有效性
      - +1分：技术的改进思路对于指定方向有借鉴意义
      - +1分：有相关开源代码/软件
      - -1分：缺乏细节，语焉不详
      - -1分：缺乏必要考虑，方案不严谨
Input Data:
   - Title: [论文标题]
   - Abstract: [摘要文本]
   - Venue: [期刊/会议名称]
Output Format (Strict JSON):
   {
   "reference_score": int,
   "technical_score": int,
   "reasoning": "简短的一句话理由，说明给分的关键点",
   "decision": "Pass" 或 "Reject" (当任一分数 >= 3 或 总分 >= 5 时为 Pass)
   }
""", 
        input_text=f"Paper title: {title}\nPaper abstract: {abstract}\nPaper periodical: {periodical}\nPaper authors: {authors}\n\nTargeted Research topic: {topic}\n", 
    )

    if score["decision"] == "Pass":
        score['title'] = title
        score['abstract'] = abstract
        score['periodical'] = periodical
        score['authors'] = authors
        scored_paper_list.append(score)

    history = state["history"] + [
        {"role": "user", "content": f"Paper title: {title}\nPaper abstract: {abstract}\nPaper periodical: {periodical}\nPaper authors: {authors}\n\nTargeted Research topic: {topic}\n"},
        {"role": "assistant", "content": score}
    ]

    return {"filtered_papers": scored_paper_list, 
            "history": history,
            "processed_count": state["processed_count"] + 1}



# class BaseParser:
#     """定义解析器的标准接口"""
#     def parse(self, raw_data):
#         raise NotImplementedError

# class ArxivParser(BaseParser):
#     def parse(self, xml_data):
#         # 处理 XML 逻辑
#         return {"title": xml_data.find('title').text, ...}

# class OpenAlexParser(BaseParser):
#     def parse(self, json_data):
#         # 处理 JSON 逻辑
#         return {"title": json_data['display_name'], ...}

# class ParserFactory:
#     """根据数据来源选择对应的解析器"""
#     @staticmethod
#     def get_parser(source):
#         parsers = {
#             "arxiv": ArxivParser(),
#             "openalex": OpenAlexParser(),
#             # ...
#         }
#         return parsers.get(source)
    

if __name__ == "__main__":
    # 初始化图
    workflow = StateGraph(GraphState)

    # 设置节点
    workflow.add_node("generator", generate_queries_func)
    workflow.add_node("aggregator", search_and_aggregate_func)
    workflow.add_node("ranker", score_and_filter_func)
    workflow.add_node("parser", download_and_parse_func)
    workflow.add_node("summarizer", summarize_and_store_func)
    workflow.add_node("notifier", send_email_func)

    # 设置连线逻辑
    workflow.set_entry_point("generator")
    workflow.add_edge("generator", "aggregator")
    workflow.add_edge("aggregator", "ranker")

    def decide_to_process(state):
        if not state["filtered_papers"]:
            return "end"  # 如果没筛出好论文，直接结束
        return "continue"

    workflow.add_conditional_edges(
        "ranker",
        decide_to_process,
        {
            "continue": "parser",
            "end": END
        }
    )

    workflow.add_edge("parser", "writer")
    workflow.add_edge("writer", "notifier")
    workflow.add_edge("notifier", END)

    app = workflow.compile()
