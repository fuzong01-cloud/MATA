from app.agents.offline import analyze_python, choose_agent, respond_offline, retrieval_query


def test_offline_answer_requires_evidence():
    result = respond_offline("明天北京天气怎么样？", [])
    assert result.status == "insufficient_evidence"
    assert "没在已导入的课程 PPT 中找到" in result.answer


def test_experiment_question_routes_to_guide_and_cites_only_evidence():
    evidence = [{"score": 0.75, "excerpt": "ADAM-4017 接线规范\nCO₂ 传感器信号线接 Vin0+，负极接 GND。"}]
    result = respond_offline("ADAM-4017 怎么接线？", evidence)
    assert choose_agent("ADAM-4017 怎么接线？") == "experiment_guide"
    assert result.status == "answered_from_slides"
    assert "Vin0+" in result.answer


def test_python_syntax_check_does_not_execute_code():
    assert analyze_python("print('hello')")["status"] == "syntax_ok"
    result = analyze_python("def broken(:\n    pass")
    assert result["status"] == "syntax_error"
    assert result["issues"][0]["line"] == 1


def test_android_cloud_failure_expands_to_course_troubleshooting_terms():
    query = retrieval_query("Android 应用无法访问云平台，怎样排查？", "Android开发")
    assert "INTERNET" in query and "Unable to resolve host" in query


def test_guidance_prefers_course_check_actions():
    evidence = [{"score": 0.75, "excerpt": "互动与问答\n点击登录按钮后提示 Unable to resolve host。\n这是典型 DNS 解析失败，请检查手机 Wi-Fi 或模拟器网络。\n请重点排查账号和密码。"}]
    result = respond_offline("Android 应用无法访问云平台怎样排查？", evidence)
    assert "请检查手机 Wi-Fi" in result.answer
    assert "请重点排查账号" in result.answer
