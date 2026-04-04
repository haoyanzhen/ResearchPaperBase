import requests
from bs4 import BeautifulSoup
from openai import OpenAI


class AIAgent:
    def __init__(self, role, llm_model, tools):
        self.role = role
        self.llm = llm_model
        self.tools = tools
        self.memory = []  # 简单短期记忆

    def perceive(self, user_input):
        # 记录输入
        self.memory.append({"role": "user", "content": user_input})
        return user_input

    def plan(self, goal):
        # 模拟 LLM 思考过程
        prompt = f"你是一个{self.role}。目标是：{goal}。请列出执行步骤。"
        # response = self.llm.generate(prompt)
        return ["搜索信息", "总结内容"] # 假设拆解后的步骤

    def act(self, action_plan):
        results = []
        for step in action_plan:
            # 根据步骤匹配对应的工具
            print(f"正在执行: {step}...")
            # result = self.tools[step].execute()
            results.append(f"{step}已完成")
        return results

    def run(self, user_query):
        input_data = self.perceive(user_query)
        steps = self.plan(input_data)
        final_result = self.act(steps)
        return "任务圆满完成！"

class WebTool:
    """网页搜索与解析工具类"""
    @staticmethod
    def fetch_and_parse(url):
        try:
            # 1. 访问网址
            headers = {'User-Agent': 'Mozilla/5.0 AI-Agent/1.0'}
            response = requests.get(url, timeout=10, headers=headers)
            response.raise_for_status()
            
            # 2. 解析 HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 移除无用标签 (脚本、样式等)
            for script_or_style in soup(["script", "style", "header", "footer", "nav"]):
                script_or_style.decompose()

            # 3. 提取纯文本并清洗多余空格
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = '\n'.join(chunk for chunk in chunks if chunk)
            
            # 返回前 1000 个字符避免 Token 溢出
            return clean_text[:1000] 
        except Exception as e:
            return f"访问失败: {str(e)}"

class EnhancedAIAgent(AIAgent):
    """增加搜索解析能力的增强型 Agent"""
    def __init__(self, role, llm_model, tools):
        super().__init__(role, llm_model, tools)
        self.web_tool = WebTool()

    def act(self, action_plan):
        results = []
        for step in action_plan:
            print(f"🛠️ 正在执行: {step}")
            
            # 逻辑增强：如果步骤涉及搜索网址
            if "访问网址" in step or "http" in step:
                # 假设我们从步骤描述中提取出了 URL
                # 实际场景中，LLM 会返回结构化的 JSON，如 {"tool": "web", "url": "..."}
                url = "https://example.com" # 示例 URL
                content = self.web_tool.fetch_and_parse(url)
                results.append(f"网页内容抓取成功：{content[:50]}...")
            else:
                results.append(f"{step}已完成")
        return results

class LLMService:
    def __init__(self, model_name="gpt-4o", api_key="YOUR_API_KEY"):
        self.client = OpenAI(api_key=api_key)
        self.model_name = model_name

    def generate(self, prompt, history=None):
        messages = []
        # 将历史记忆加入上下文
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0.7  # 控制随机性
        )
        return response.choices[0].message.content

# 实例化并填入 Agent
llm = LLMService(model_name="gpt-4o", api_key="sk-xxxx")
agent = AIAgent(role="论文查询师", llm_model=llm, tools=[])
# result = agent.run("请帮我查一下这个网站的内容：https://www.wikipedia.org")