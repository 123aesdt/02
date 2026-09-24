import os
import threading
import time

# 缓存已经加载的模型，避免每次提问都重新加载
_LOCAL_QWEN_CACHE = {}

# 防止多个请求同时重复加载模型
_LOCAL_QWEN_LOCK = threading.Lock()


def _load_local_qwen(model_path: str):
    """从算力云本地目录加载 Qwen 模型。"""

    # 如果模型已经加载，直接使用缓存
    cached = _LOCAL_QWEN_CACHE.get(model_path)
    if cached:
        return cached

    with _LOCAL_QWEN_LOCK:
        # 获得锁以后再次检查，避免其他线程已经完成加载
        cached = _LOCAL_QWEN_CACHE.get(model_path)
        if cached:
            return cached

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        # 有显卡时使用 CUDA 和半精度，提高推理速度并减少显存占用
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32

        # 从算力云本地目录读取分词器
        tokenizer = AutoTokenizer.from_pretrained(
            model_path,
            local_files_only=True,
        )

        # 从算力云本地目录读取模型
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            local_files_only=True,
            dtype=dtype,
        )

        # 将模型放到显卡或CPU，并切换到推理模式
        model = model.to(device).eval()

        # 保存到缓存
        cached = (tokenizer, model, device)
        _LOCAL_QWEN_CACHE[model_path] = cached

        return cached


def _generate_local_qwen(message: str, opt) -> str:
    """将用户的问题交给本地 Qwen，并返回模型答案。"""

    import torch

    # 优先读取配置文件中的模型地址
    # 没有配置时默认使用 /root/autodl-tmp/dir
    model_path = (
        getattr(opt, "llm_model", "")
        or os.getenv("LOCAL_QWEN_MODEL", "/root/autodl-tmp/dir")
    )

    tokenizer, model, device = _load_local_qwen(model_path)

    # 构建医疗助手对话
    messages = [
        {
            "role": "system",
            "content": (
                "你是一名中文医疗健康咨询助手。"
                "回答要简洁、自然、便于口播；"
                "只提供一般健康信息，不做确诊，"
                "遇到急症或高风险情况提醒用户及时就医。"
            ),
        },
        {
            "role": "user",
            "content": message,
        },
    ]

    # 使用Qwen模型规定的聊天格式生成提示词
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    # 将文字转换成模型能够处理的数字
    inputs = tokenizer([prompt], return_tensors="pt")
    inputs = {
        name: tensor.to(device)
        for name, tensor in inputs.items()
    }

    # 记录输入长度，后面只截取模型新生成的内容
    prompt_length = inputs["input_ids"].shape[1]

    # 关闭梯度计算，降低推理显存占用
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=256,                 # 最多生成256个token
            do_sample=False,                    # 使用稳定输出
            pad_token_id=tokenizer.eos_token_id,
        )

    # 删除原始提示词，只返回模型生成的答案
    answer = tokenizer.decode(
        output[0][prompt_length:],
        skip_special_tokens=True,
    )

    return answer.strip()


def llm_response(message, avatar_session, datainfo={}):
    """生成回答，并将答案交给数字人播报。"""

    try:
        opt = avatar_session.opt
        start_time = time.perf_counter()

        # 判断当前是否配置为本地 Qwen
        if getattr(opt, "llm_provider", "") == "local_qwen":

            # 让Qwen生成答案，不再直接复读用户原话
            answer = _generate_local_qwen(message, opt)

            if answer:
                # 把回答放进数字人的消息队列
                # 后续由TTS生成语音，再由Wav2Lip驱动口型
                avatar_session.put_msg_txt(answer, datainfo)

            print(
                "Qwen回答耗时：",
                time.perf_counter() - start_time,
                "秒",
            )
            return

    except Exception as error:
        print("本地Qwen调用失败：", error)