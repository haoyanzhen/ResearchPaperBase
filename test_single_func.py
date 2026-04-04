from paperpush import GraphState, generate_queries_func

if __name__ == "__main__":
    test_state: GraphState = {
        "model": "deepseek-chat",            # 或者 "llama3" (如果用 Ollama)
        "provider": "openai",                # 或 "ollama"
        "api_key": "sk-a30d19e7c6f24e3d9ecee149f043985d",
        # "base_url": "https://api.deepseek.com",
        "base_url": "https://api.deepseek.com/v1/chat/completions",
        "topic": "密集星场混叠星像（恒星）的分离、定位与测光",
        "queries": [],
        "raw_results": [],
        "filtered_papers": [],
        "processed_count": 0,
        "final_db_update": False
    }

    print("--- 开始调试 generator 节点 ---")
    output = generate_queries_func(test_state)

    print("\n[LLM 返回原始结果]:")
    print(output["queries"])
    print(f"\n[处理计数]: {output['processed_count']}")