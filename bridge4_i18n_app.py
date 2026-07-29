#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
앱 화면 문구 다국어 테이블

언어를 중국어로 고르면 리포트만이 아니라 화면 전체가 중국어여야 한다.
버튼·입력칸 이름이 한국어로 남아 있으면 중국인 사용자는 조작할 수 없다.

일부러 한국어로 남기는 것 두 가지
  1. 고용주에게 보여줄 질문 문장 — 그게 목적이다
  2. 공고에서 인용한 원문 — 증거이므로 번역하면 안 된다

번역하지 않는 것
  구·군 이름, 업종·직종 분류값 같은 데이터 값은 모델의 학습 범주라 번역하면
  예측이 깨진다. 화면에는 원값을 그대로 보여준다. 단 '정보없음' 선택지만
  표시용 문구를 언어별로 바꾼다(값은 그대로 '정보없음').
"""

from __future__ import annotations

APP: dict[str, dict[str, str]] = {
    "ko": {
        'cond_only': '이 공고는 상세요강이 이미지로 올라와 본문 글자가 없습니다. 대신 채용 사이트에 입력된 아래 근로조건을 근거로 진단합니다.',
        'cond_hdr': '공고가 밝힌 근로조건',
        "pv_run": '이 공고 근로조건 진단하기',
        'src': '출처',
        'src_pub': '고용24 (공공)',
        'src_priv': '알바몬·알바천국',
        'pv_basis': '같은 직종 알바 공고 {n}건의 **실측 시급 분포**입니다. 모델 예측이 아닙니다.',
        'pv_all': '직종 표본이 얇아 **민간 공고 전체** {n}건 분포를 씁니다.',
        'pv_why': "이 공고는 알바 사이트 공고입니다. 임금 예측 모델은 고용24 공공 공고로 학습했고 기업정보 피처 14개가 알바 공고에는 없습니다. 그대로 쓰면 최저임금을 정상 지급하는 알바가 '적정 미달'로 나옵니다. 그래서 모델 대신 실제 알바 공고 시급 분포와 비교합니다.",
        'pv_range': '알바 실측 시급',
        'pv_noimg': '이 공고는 본문이 이미지뿐이어서 근로조건 진단을 할 수 없습니다. 임금 비교만 보여드립니다.',
        'pv_dup': '같은 공고가 여러 번 올라온 건입니다(재게시).',
        'pv_nocomp': '알바 사이트는 회사명을 제공하지 않아 비워 둡니다.',
        "url_hdr": '링크로 불러오기',
        "url_lbl": '알바몬 공고 링크',
        "url_ph": 'https://www.albamon.com/jobs/detail/...',
        "url_btn": '링크 불러오기',
        "url_note": '링크를 넣으면 공고 내용과 조건을 자동으로 채웁니다. 안 되면 아래에 직접 붙여넣으세요.',
        "url_ok": '불러왔습니다 — 아래 내용을 확인하고 필요하면 고치세요.',
        "url_fail": '링크를 읽지 못했습니다. 아래에 공고 내용을 직접 붙여넣어 주세요.',
        "url_todo": '링크 자동 수집은 아직 준비 중입니다. 아래에 공고 내용을 직접 붙여넣어 주세요.',
        "url_or": '또는 직접 붙여넣기',
        "viz_hdr": '📊 근거 보기',
        "pct": '유사 공고 중 상위 {p}%',
        "m_range_short": '적정 시급',
        "m_hourly": '환산 시급',
        "auto_found": '공고에서 임금을 읽었습니다 — "{raw}" ({kind}). 아래에서 직접 고치면 그 값이 쓰입니다.',
        "subtitle": "부산 지역 외국인 유학생·근로자를 위한 **채용공고 근로조건 분석 · 권익 보호 AI**",
        "tab_chat": "💬 공고 물어보기", "tab_db": "📚 수집 공고", "tab_perf": "📈 모델 성능",
        "sb_lang": "언어", "sb_key": "OpenAI API 키",
        "key_ph": "키를 붙여넣으세요", "key_lbl": "sk- 로 시작하는 키",
        "key_help": "대화에 필요합니다. 입력한 키는 이 세션에만 남고 저장되지 않습니다.",
        "key_none": "키가 없습니다. 임금 예측은 그대로 되지만 대화는 되지 않습니다.",
        "key_ok": "키 확인됨",
        "key_note": "키는 세션 메모리에만 둡니다. 서버에 저장하지 않습니다.",
        "sb_perf": "모델 성능",
        "step1": "① 공고 붙여넣기 · 조건 입력",
        "body_lbl": "채용공고 본문",
        "body_ph": "예) 주간 근무 / 시급 회사 내규에 따름 (월 220만 원 이상 가능) / 초보 가능 / 기숙사 제공",
        "wage_hdr": "공고에 적힌 임금", "wage_kind": "임금 형태", "wage_amt": "금액",
        "k_none": "미표기", "k_month": "월급", "k_hour": "시급", "k_year": "연봉", "k_day": "일급",
        "cond_hdr": "근무 조건", "c_gu": "근무 지역 (구·군)", "c_weekly": "주당 근로시간",
        "c_days": "주당 근무일수", "c_ksco": "직종 대분류", "c_emp": "기업 근로자수",
        "c_size": "기업 규모", "c_more": "더 자세히 (선택) — 채우면 예측이 정확해집니다",
        "c_ind": "기업 업종", "c_job": "모집 직종", "c_career": "경력",
        "c_edu": "학력", "c_type": "고용형태",
        "c_emp_help": "예측에 가장 큰 영향을 주는 항목입니다. 모르면 0",
        "no_info": "정보없음",
        "btn_start": "이 공고로 시작하기", "btn_reset": "다른 공고로 바꾸기",
        "m_range": "적정 시급 (80%)", "m_month": "월 환산", "m_posted": "공고 표기 임금",
        "m_reliab": "신뢰도", "m_hold": "제시 보류", "m_notposted": "미표기",
        "spinner": "근로조건 7가지 항목을 분석하는 중…",
        "rep_open": "📋 상세 리포트 보기",
        "chat_hdr": "💬 공고에 대해 물어보세요",
        "chat_note": "**어떤 언어로 물어도 그 언어로 답합니다.** 공고에 없는 내용은 '없다'고 알려주고, 사장님께 물어볼 한국어 문장을 함께 줍니다.",
        "chat_ph": "질문을 입력하세요",
        "chat_needkey": "OpenAI API 키가 필요합니다. 왼쪽에 키를 넣어 주세요.",
        "db_note": "이미 수집·진단해 둔 공고입니다. 진단은 사전 계산본이라 비용이 없고, 대화만 API 를 씁니다.",
        "db_search": "기업명 · 공고제목 검색", "db_search_ph": "예: 요양보호사, 경비, 제조",
        "db_gu": "구·군", "db_all": "전체", "db_scope": "표시 범위",
        "db_s1": "확인 질문까지 있는 공고", "db_s2": "진단 있는 공고", "db_s3": "전체",
        "db_sel": "공고 선택 (앞 300건)", "db_none": "조건에 맞는 공고가 없습니다.",
        "db_orig": "공고 원문", "db_qonly": "면접장에서 보여줄 질문만 크게 보기",
        "db_count": "건",
    },
    "en": {
        'cond_only': "This posting's details were uploaded as an image, so there is no body text. The working conditions entered on the job board are used instead.",
        'cond_hdr': 'Working conditions stated in the posting',
        "pv_run": 'Diagnose this posting',
        'src': 'Source',
        'src_pub': 'Work24 (public)',
        'src_priv': 'Albamon · Alba',
        'pv_basis': 'This is the **observed hourly-wage distribution** of {n} part-time postings in the same occupation — not a model prediction.',
        'pv_all': 'The occupation sample is thin, so **all {n} private postings** are used.',
        'pv_why': 'This is a part-time job-board posting. The wage model was trained on Work24 public postings and 14 of its company features do not exist on job boards. Using it would flag lawfully minimum-wage jobs as underpaid. So we compare against the actual distribution instead.',
        'pv_range': 'Observed hourly range',
        'pv_noimg': "This posting's body is images only, so conditions cannot be diagnosed. Only the wage comparison is shown.",
        'pv_dup': 'This posting was re-listed multiple times.',
        'pv_nocomp': 'Job boards do not expose the company name, so it is left blank.',
        "url_hdr": 'Load from a link',
        "url_lbl": 'Albamon posting URL',
        "url_ph": 'https://www.albamon.com/jobs/detail/...',
        "url_btn": 'Load link',
        "url_note": 'Paste a link and the posting text and conditions are filled in for you. If it fails, paste the text below instead.',
        "url_ok": 'Loaded — check the fields below and correct anything that is off.',
        "url_fail": 'Could not read the link. Please paste the posting text below instead.',
        "url_todo": 'Loading from a link is not ready yet. Please paste the posting text below.',
        "url_or": 'or paste it yourself',
        "viz_hdr": '📊 See the evidence',
        "pct": 'Higher than {p}% of similar postings',
        "m_range_short": 'Fair hourly',
        "m_hourly": 'Converted hourly',
        "auto_found": 'Wage detected in the posting — "{raw}" ({kind}). Override it below if needed.',
        "subtitle": "**Job-posting analysis and worker-rights AI** for international students and workers in Busan",
        "tab_chat": "💬 Ask about a posting", "tab_db": "📚 Collected postings",
        "tab_perf": "📈 Model performance",
        "sb_lang": "Language", "sb_key": "OpenAI API key",
        "key_ph": "Paste your key", "key_lbl": "Key starting with sk-",
        "key_help": "Needed for the chat. Your key stays in this session only and is not saved.",
        "key_none": "No key. Wage prediction still works, but the chat does not.",
        "key_ok": "Key detected",
        "key_note": "The key is kept in session memory only, never stored on a server.",
        "sb_perf": "Model performance",
        "step1": "① Paste the posting · enter conditions",
        "body_lbl": "Job posting text",
        "body_ph": "e.g. Day shift / wage per company policy (2.2M KRW+/month possible) / no experience needed / dormitory provided",
        "wage_hdr": "Wage stated in the posting", "wage_kind": "Wage type", "wage_amt": "Amount",
        "k_none": "not stated", "k_month": "monthly", "k_hour": "hourly",
        "k_year": "annual", "k_day": "daily",
        "cond_hdr": "Working conditions", "c_gu": "District in Busan",
        "c_weekly": "Hours per week", "c_days": "Days per week",
        "c_ksco": "Occupation group", "c_emp": "Company headcount",
        "c_size": "Company size", "c_more": "More detail (optional) — improves the prediction",
        "c_ind": "Industry", "c_job": "Job category", "c_career": "Experience",
        "c_edu": "Education", "c_type": "Employment type",
        "c_emp_help": "The single most influential field. Put 0 if unknown.",
        "no_info": "unknown",
        "btn_start": "Start with this posting", "btn_reset": "Use a different posting",
        "m_range": "Fair hourly (80%)", "m_month": "Per month", "m_posted": "Wage as posted",
        "m_reliab": "Confidence", "m_hold": "not shown", "m_notposted": "not stated",
        "spinner": "Checking the 7 working-condition items…",
        "rep_open": "📋 Open the full report",
        "chat_hdr": "💬 Ask anything about this posting",
        "chat_note": "**Ask in any language and the answer comes back in that language.** If the posting does not say, it will tell you so and give you a Korean sentence to ask the employer.",
        "chat_ph": "Type your question",
        "chat_needkey": "An OpenAI API key is required. Please enter one on the left.",
        "db_note": "Postings we already collected and analysed. The analysis is precomputed (no cost); only the chat uses the API.",
        "db_search": "Search company or title",
        "db_search_ph": "e.g. care worker, security, factory",
        "db_gu": "District", "db_all": "All", "db_scope": "Show",
        "db_s1": "With questions ready", "db_s2": "With analysis", "db_s3": "All",
        "db_sel": "Pick a posting (first 300)",
        "db_none": "No postings match. Try widening the filter.",
        "db_orig": "Original posting text", "db_qonly": "Show just the questions, large",
        "db_count": "postings",
    },
    "zh": {
        'cond_only': '该公告的详细内容是以图片上传的，没有正文文字。因此改用招聘网站上填写的以下劳动条件进行诊断。',
        'cond_hdr': '公告写明的劳动条件',
        "pv_run": '诊断这条公告的劳动条件',
        'src': '来源',
        'src_pub': 'Work24（公共）',
        'src_priv': 'Albamon · Alba',
        'pv_basis': '这是同一职业 {n} 条兼职公告的**实测时薪分布**，不是模型预测。',
        'pv_all': '该职业样本过少，因此使用**全部 {n} 条**民间公告的分布。',
        'pv_why': '这是兼职网站的公告。工资预测模型是用 Work24 公共公告训练的，其中 14 个企业信息特征在兼职网站上并不存在。直接使用会把合法支付最低工资的兼职判为「低于合理水平」。因此我们改用实际兼职公告的时薪分布进行比较。',
        'pv_range': '兼职实测时薪',
        'pv_noimg': '该公告正文全是图片，无法进行劳动条件诊断，仅显示工资比较。',
        'pv_dup': '同一公告被重复发布过多次。',
        'pv_nocomp': '兼职网站不提供公司名称，故留空。',
        "url_hdr": '通过链接载入',
        "url_lbl": 'Albamon 招聘链接',
        "url_ph": 'https://www.albamon.com/jobs/detail/...',
        "url_btn": '载入链接',
        "url_note": '粘贴链接后会自动填入公告内容和条件。如果不行，请在下方直接粘贴内容。',
        "url_ok": '已载入 — 请确认下面的内容，必要时可修改。',
        "url_fail": '无法读取该链接。请在下方直接粘贴公告内容。',
        "url_todo": '链接自动采集功能尚在准备中。请在下方直接粘贴公告内容。',
        "url_or": '或者直接粘贴',
        "viz_hdr": '📊 查看依据',
        "pct": '高于同类公告的 {p}%',
        "m_range_short": '合理时薪',
        "m_hourly": '折合时薪',
        "auto_found": '已从招聘信息中读取工资 — "{raw}"（{kind}）。如需修改，请在下方直接指定。',
        "subtitle": "为在釜山的外国留学生和劳动者提供的**招聘信息劳动条件分析 · 权益保护 AI**",
        "tab_chat": "💬 询问招聘信息", "tab_db": "📚 已收集的招聘信息",
        "tab_perf": "📈 模型性能",
        "sb_lang": "语言", "sb_key": "OpenAI API 密钥",
        "key_ph": "请粘贴密钥", "key_lbl": "以 sk- 开头的密钥",
        "key_help": "对话功能需要密钥。输入的密钥只保存在本次会话中，不会被存储。",
        "key_none": "没有密钥。工资预测仍可使用，但无法进行对话。",
        "key_ok": "已确认密钥",
        "key_note": "密钥仅保存在会话内存中，不会存到服务器。",
        "sb_perf": "模型性能",
        "step1": "① 粘贴招聘信息 · 输入条件",
        "body_lbl": "招聘信息正文",
        "body_ph": "例）白班 / 时薪按公司规定（月薪可达220万韩元以上）/ 无经验可 / 提供宿舍",
        "wage_hdr": "招聘信息中的工资", "wage_kind": "工资形式", "wage_amt": "金额",
        "k_none": "未写明", "k_month": "月薪", "k_hour": "时薪", "k_year": "年薪", "k_day": "日薪",
        "cond_hdr": "工作条件", "c_gu": "工作地区（区·郡）", "c_weekly": "每周工作时间",
        "c_days": "每周工作天数", "c_ksco": "职业大类", "c_emp": "企业员工人数",
        "c_size": "企业规模", "c_more": "填写更多信息（可选）— 预测会更准确",
        "c_ind": "企业行业", "c_job": "招聘职种", "c_career": "经验",
        "c_edu": "学历", "c_type": "雇佣形式",
        "c_emp_help": "对预测影响最大的项目。不清楚就填 0。",
        "no_info": "无信息",
        "btn_start": "用这条信息开始", "btn_reset": "换成其他招聘信息",
        "m_range": "合理时薪（80%）", "m_month": "折合月薪", "m_posted": "公告标示工资",
        "m_reliab": "可信度", "m_hold": "暂不提供", "m_notposted": "未写明",
        "spinner": "正在分析7项劳动条件…",
        "rep_open": "📋 查看详细报告",
        "chat_hdr": "💬 有什么想问的都可以问",
        "chat_note": "**用哪种语言提问，就用那种语言回答。** 招聘信息里没有写的内容会明确告知，并附上可以直接向雇主出示的韩语问句。",
        "chat_ph": "请输入问题",
        "chat_needkey": "需要 OpenAI API 密钥。请在左侧输入。",
        "db_note": "已经收集并分析过的招聘信息。分析结果是预先算好的，不产生费用；只有对话会使用 API。",
        "db_search": "搜索企业名·公告标题", "db_search_ph": "例：疗养保护师、保安、制造",
        "db_gu": "区·郡", "db_all": "全部", "db_scope": "显示范围",
        "db_s1": "已备好提问的公告", "db_s2": "已分析的公告", "db_s3": "全部",
        "db_sel": "选择公告（前300条）", "db_none": "没有符合条件的公告。请放宽筛选条件。",
        "db_orig": "公告原文", "db_qonly": "只看问题（大字显示）",
        "db_count": "条",
    },
    "vi": {
        'cond_only': 'Chi tiết của tin này được đăng dưới dạng hình ảnh nên không có văn bản. Thay vào đó, các điều kiện làm việc nhập trên trang tuyển dụng được dùng.',
        'cond_hdr': 'Điều kiện làm việc tin đã nêu',
        "pv_run": 'Chẩn đoán điều kiện của tin này',
        'src': 'Nguồn',
        'src_pub': 'Work24 (công)',
        'src_priv': 'Albamon · Alba',
        'pv_basis': 'Đây là **phân bố lương giờ thực đo** của {n} tin tuyển dụng bán thời gian cùng ngành nghề — không phải dự đoán của mô hình.',
        'pv_all': 'Mẫu theo ngành quá ít nên dùng phân bố của **toàn bộ {n} tin** tư nhân.',
        'pv_why': 'Đây là tin từ trang tuyển dụng bán thời gian. Mô hình dự đoán lương được huấn luyện trên tin công của Work24, và 14 đặc trưng doanh nghiệp của nó không tồn tại trên các trang này. Dùng nguyên sẽ khiến việc trả đúng lương tối thiểu bị coi là thấp. Vì vậy chúng tôi so sánh với phân bố thực tế.',
        'pv_range': 'Lương giờ thực đo',
        'pv_noimg': 'Nội dung tin chỉ có hình ảnh nên không thể chẩn đoán điều kiện làm việc. Chỉ hiển thị so sánh lương.',
        'pv_dup': 'Tin này đã được đăng lại nhiều lần.',
        'pv_nocomp': 'Trang tuyển dụng không cung cấp tên công ty nên để trống.',
        "url_hdr": 'Tải từ đường liên kết',
        "url_lbl": 'Đường liên kết tin Albamon',
        "url_ph": 'https://www.albamon.com/jobs/detail/...',
        "url_btn": 'Tải liên kết',
        "url_note": 'Dán liên kết và nội dung tin cùng điều kiện sẽ được tự động điền. Nếu không được, hãy dán nội dung ở bên dưới.',
        "url_ok": 'Đã tải — hãy kiểm tra các mục bên dưới và sửa nếu cần.',
        "url_fail": 'Không đọc được liên kết. Vui lòng dán nội dung tin ở bên dưới.',
        "url_todo": 'Chức năng tải từ liên kết chưa sẵn sàng. Vui lòng dán nội dung tin ở bên dưới.',
        "url_or": 'hoặc tự dán nội dung',
        "viz_hdr": '📊 Xem căn cứ',
        "pct": 'Cao hơn {p}% tin tương tự',
        "m_range_short": 'Lương giờ hợp lý',
        "m_hourly": 'Lương giờ quy đổi',
        "auto_found": 'Đã đọc mức lương từ tin tuyển dụng — "{raw}" ({kind}). Có thể sửa ở bên dưới.',
        "subtitle": "**AI phân tích điều kiện lao động và bảo vệ quyền lợi** cho du học sinh và người lao động nước ngoài tại Busan",
        "tab_chat": "💬 Hỏi về tin tuyển dụng", "tab_db": "📚 Tin đã thu thập",
        "tab_perf": "📈 Hiệu năng mô hình",
        "sb_lang": "Ngôn ngữ", "sb_key": "Khóa API OpenAI",
        "key_ph": "Dán khóa của bạn", "key_lbl": "Khóa bắt đầu bằng sk-",
        "key_help": "Cần cho phần trò chuyện. Khóa chỉ lưu trong phiên này và không được lưu trữ.",
        "key_none": "Chưa có khóa. Dự đoán lương vẫn hoạt động nhưng không trò chuyện được.",
        "key_ok": "Đã nhận khóa",
        "key_note": "Khóa chỉ nằm trong bộ nhớ phiên, không lưu lên máy chủ.",
        "sb_perf": "Hiệu năng mô hình",
        "step1": "① Dán tin tuyển dụng · nhập điều kiện",
        "body_lbl": "Nội dung tin tuyển dụng",
        "body_ph": "VD) Làm ca ngày / lương theo quy định công ty (có thể trên 2,2 triệu won/tháng) / không cần kinh nghiệm / có ký túc xá",
        "wage_hdr": "Lương ghi trong tin", "wage_kind": "Hình thức lương", "wage_amt": "Số tiền",
        "k_none": "không ghi", "k_month": "lương tháng", "k_hour": "lương giờ",
        "k_year": "lương năm", "k_day": "lương ngày",
        "cond_hdr": "Điều kiện làm việc", "c_gu": "Khu vực làm việc (gu·gun)",
        "c_weekly": "Số giờ mỗi tuần", "c_days": "Số ngày mỗi tuần",
        "c_ksco": "Nhóm nghề", "c_emp": "Số lao động của công ty",
        "c_size": "Quy mô công ty",
        "c_more": "Nhập chi tiết hơn (tùy chọn) — dự đoán sẽ chính xác hơn",
        "c_ind": "Ngành của công ty", "c_job": "Vị trí tuyển", "c_career": "Kinh nghiệm",
        "c_edu": "Học vấn", "c_type": "Loại hợp đồng",
        "c_emp_help": "Đây là mục ảnh hưởng lớn nhất đến dự đoán. Không biết thì để 0.",
        "no_info": "không có thông tin",
        "btn_start": "Bắt đầu với tin này", "btn_reset": "Đổi sang tin khác",
        "m_range": "Lương giờ hợp lý (80%)", "m_month": "Quy ra tháng",
        "m_posted": "Lương ghi trong tin", "m_reliab": "Độ tin cậy",
        "m_hold": "chưa đưa ra", "m_notposted": "không ghi",
        "spinner": "Đang phân tích 7 hạng mục điều kiện lao động…",
        "rep_open": "📋 Xem báo cáo chi tiết",
        "chat_hdr": "💬 Hãy hỏi bất cứ điều gì về tin này",
        "chat_note": "**Bạn hỏi bằng ngôn ngữ nào thì được trả lời bằng ngôn ngữ đó.** Nội dung không có trong tin sẽ được nói rõ là không có, kèm câu tiếng Hàn để bạn hỏi chủ doanh nghiệp.",
        "chat_ph": "Nhập câu hỏi",
        "chat_needkey": "Cần khóa API OpenAI. Vui lòng nhập ở bên trái.",
        "db_note": "Những tin chúng tôi đã thu thập và phân tích. Kết quả phân tích được tính trước nên không tốn phí; chỉ phần trò chuyện dùng API.",
        "db_search": "Tìm theo tên công ty · tiêu đề",
        "db_search_ph": "VD: điều dưỡng, bảo vệ, sản xuất",
        "db_gu": "Gu·Gun", "db_all": "Tất cả", "db_scope": "Phạm vi hiển thị",
        "db_s1": "Tin đã có câu hỏi", "db_s2": "Tin đã phân tích", "db_s3": "Tất cả",
        "db_sel": "Chọn tin (300 tin đầu)",
        "db_none": "Không có tin nào phù hợp. Hãy mở rộng điều kiện.",
        "db_orig": "Nguyên văn tin tuyển dụng", "db_qonly": "Chỉ xem câu hỏi, cỡ lớn",
        "db_count": "tin",
    },
    "ja": {
        'cond_only': 'この求人は詳細が画像で登録されており本文テキストがありません。代わりに求人サイトに入力された以下の労働条件を根拠に診断します。',
        'cond_hdr': '求人が示した労働条件',
        "pv_run": 'この求人の労働条件を診断',
        'src': '出典',
        'src_pub': 'Work24（公共）',
        'src_priv': 'Albamon · Alba',
        'pv_basis': '同じ職種のアルバイト求人 {n} 件の**実測時給分布**です。モデル予測ではありません。',
        'pv_all': '職種の標本が少ないため、**民間求人全体 {n} 件**の分布を使います。',
        'pv_why': 'これはアルバイト求人サイトの募集です。賃金予測モデルは Work24 の公共求人で学習しており、企業情報の特徴 14 個がアルバイトサイトには存在しません。そのまま使うと、最低賃金を適正に支払っている求人が「適正未満」と出ます。そのため実際のアルバイト時給分布と比較します。',
        'pv_range': 'アルバイト実測時給',
        'pv_noimg': 'この求人は本文が画像のみのため労働条件の診断ができません。賃金比較のみ表示します。',
        'pv_dup': '同じ求人が複数回掲載されています。',
        'pv_nocomp': '求人サイトは会社名を公開しないため空欄です。',
        "url_hdr": 'リンクから読み込む',
        "url_lbl": 'Albamon 求人リンク',
        "url_ph": 'https://www.albamon.com/jobs/detail/...',
        "url_btn": 'リンクを読み込む',
        "url_note": 'リンクを貼ると求人内容と条件を自動で入力します。うまくいかない場合は下に直接貼り付けてください。',
        "url_ok": '読み込みました — 下の内容を確認し、必要なら修正してください。',
        "url_fail": 'リンクを読み取れませんでした。下に求人内容を直接貼り付けてください。',
        "url_todo": 'リンクからの自動取得はまだ準備中です。下に求人内容を直接貼り付けてください。',
        "url_or": 'または直接貼り付け',
        "viz_hdr": '📊 根拠を見る',
        "pct": '同種求人の {p}% より高い',
        "m_range_short": '適正時給',
        "m_hourly": '時給換算',
        "auto_found": '求人から賃金を読み取りました — 「{raw}」（{kind}）。下で直接変更もできます。',
        "subtitle": "釜山の外国人留学生・労働者のための**求人労働条件分析・権益保護 AI**",
        "tab_chat": "💬 求人について聞く", "tab_db": "📚 収集した求人",
        "tab_perf": "📈 モデル性能",
        "sb_lang": "言語", "sb_key": "OpenAI API キー",
        "key_ph": "キーを貼り付けてください", "key_lbl": "sk- で始まるキー",
        "key_help": "対話に必要です。入力したキーはこのセッションにのみ残り、保存されません。",
        "key_none": "キーがありません。賃金予測は使えますが対話はできません。",
        "key_ok": "キーを確認しました",
        "key_note": "キーはセッションメモリにのみ置き、サーバーには保存しません。",
        "sb_perf": "モデル性能",
        "step1": "① 求人を貼り付け・条件を入力",
        "body_lbl": "求人本文",
        "body_ph": "例）日勤 / 時給は社内規定による（月220万ウォン以上可能）/ 未経験可 / 寮あり",
        "wage_hdr": "求人に書かれた賃金", "wage_kind": "賃金の形態", "wage_amt": "金額",
        "k_none": "記載なし", "k_month": "月給", "k_hour": "時給", "k_year": "年俸", "k_day": "日給",
        "cond_hdr": "労働条件", "c_gu": "勤務地域（区・郡）", "c_weekly": "週の労働時間",
        "c_days": "週の勤務日数", "c_ksco": "職種大分類", "c_emp": "企業の従業員数",
        "c_size": "企業規模", "c_more": "さらに詳しく（任意）— 入力すると予測が正確になります",
        "c_ind": "企業の業種", "c_job": "募集職種", "c_career": "経験",
        "c_edu": "学歴", "c_type": "雇用形態",
        "c_emp_help": "予測に最も影響する項目です。分からなければ 0。",
        "no_info": "情報なし",
        "btn_start": "この求人で始める", "btn_reset": "別の求人に変える",
        "m_range": "適正時給（80%）", "m_month": "月額換算", "m_posted": "求人表示の賃金",
        "m_reliab": "信頼度", "m_hold": "提示保留", "m_notposted": "記載なし",
        "spinner": "労働条件7項目を分析しています…",
        "rep_open": "📋 詳細レポートを見る",
        "chat_hdr": "💬 この求人について何でも聞いてください",
        "chat_note": "**質問した言語と同じ言語で回答します。** 求人に書かれていないことは「書かれていない」と伝え、社長に見せる韓国語の文もあわせて出します。",
        "chat_ph": "質問を入力してください",
        "chat_needkey": "OpenAI API キーが必要です。左側に入力してください。",
        "db_note": "すでに収集・分析した求人です。分析結果は事前計算なので費用はかからず、対話のみ API を使います。",
        "db_search": "企業名・求人タイトル検索", "db_search_ph": "例：介護、警備、製造",
        "db_gu": "区・郡", "db_all": "すべて", "db_scope": "表示範囲",
        "db_s1": "質問まで用意された求人", "db_s2": "分析済みの求人", "db_s3": "すべて",
        "db_sel": "求人を選択（先頭300件）",
        "db_none": "条件に合う求人がありません。範囲を広げてください。",
        "db_orig": "求人の原文", "db_qonly": "質問だけ大きく表示",
        "db_count": "件",
    },
    "es": {
        'cond_only': 'Los detalles de esta oferta se subieron como imagen, así que no hay texto. Se usan las condiciones laborales indicadas en el portal.',
        'cond_hdr': 'Condiciones laborales indicadas',
        "pv_run": 'Diagnosticar esta oferta',
        'src': 'Fuente',
        'src_pub': 'Work24 (público)',
        'src_priv': 'Albamon · Alba',
        'pv_basis': 'Esta es la **distribución observada del salario por hora** de {n} ofertas de tiempo parcial en la misma ocupación, no una predicción del modelo.',
        'pv_all': 'La muestra de la ocupación es escasa, así que se usan **las {n} ofertas** privadas.',
        'pv_why': 'Esta es una oferta de un portal de empleo parcial. El modelo se entrenó con ofertas públicas de Work24 y 14 de sus variables de empresa no existen en estos portales. Usarlo marcaría como bajos los empleos que pagan legalmente el mínimo. Por eso comparamos con la distribución real.',
        'pv_range': 'Salario/hora observado',
        'pv_noimg': 'El cuerpo de esta oferta solo tiene imágenes, así que no se pueden diagnosticar las condiciones. Solo se muestra la comparación salarial.',
        'pv_dup': 'Esta oferta se volvió a publicar varias veces.',
        'pv_nocomp': 'Los portales no muestran el nombre de la empresa, así que queda vacío.',
        "url_hdr": 'Cargar desde un enlace',
        "url_lbl": 'Enlace de la oferta en Albamon',
        "url_ph": 'https://www.albamon.com/jobs/detail/...',
        "url_btn": 'Cargar enlace',
        "url_note": 'Pega un enlace y se rellenarán el texto y las condiciones. Si falla, pega el texto abajo.',
        "url_ok": 'Cargado — revisa los campos de abajo y corrige lo que haga falta.',
        "url_fail": 'No se pudo leer el enlace. Pega el texto de la oferta abajo.',
        "url_todo": 'La carga desde enlace aún no está lista. Pega el texto de la oferta abajo.',
        "url_or": 'o pégalo tú mismo',
        "viz_hdr": '📊 Ver la evidencia',
        "pct": 'Supera al {p}% de ofertas similares',
        "m_range_short": 'Salario/hora justo',
        "m_hourly": 'Equivalente por hora',
        "auto_found": 'Salario detectado en la oferta — "{raw}" ({kind}). Puedes cambiarlo abajo.',
        "subtitle": "**IA de análisis de condiciones laborales y protección de derechos** para estudiantes y trabajadores extranjeros en Busan",
        "tab_chat": "💬 Preguntar sobre una oferta", "tab_db": "📚 Ofertas recopiladas",
        "tab_perf": "📈 Rendimiento del modelo",
        "sb_lang": "Idioma", "sb_key": "Clave API de OpenAI",
        "key_ph": "Pega tu clave", "key_lbl": "Clave que empieza por sk-",
        "key_help": "Necesaria para el chat. Tu clave solo queda en esta sesión y no se guarda.",
        "key_none": "Sin clave. La predicción salarial funciona, pero el chat no.",
        "key_ok": "Clave detectada",
        "key_note": "La clave solo se mantiene en memoria de sesión, nunca en un servidor.",
        "sb_perf": "Rendimiento del modelo",
        "step1": "① Pega la oferta · introduce las condiciones",
        "body_lbl": "Texto de la oferta",
        "body_ph": "Ej.) Turno de día / salario según normativa interna (posible más de 2,2 millones de wones/mes) / sin experiencia / alojamiento incluido",
        "wage_hdr": "Salario indicado en la oferta", "wage_kind": "Tipo de salario",
        "wage_amt": "Importe",
        "k_none": "no indicado", "k_month": "mensual", "k_hour": "por hora",
        "k_year": "anual", "k_day": "diario",
        "cond_hdr": "Condiciones de trabajo", "c_gu": "Distrito de Busan",
        "c_weekly": "Horas por semana", "c_days": "Días por semana",
        "c_ksco": "Grupo ocupacional", "c_emp": "Número de empleados",
        "c_size": "Tamaño de la empresa", "c_more": "Más detalle (opcional) — mejora la predicción",
        "c_ind": "Sector de la empresa", "c_job": "Puesto ofertado", "c_career": "Experiencia",
        "c_edu": "Estudios", "c_type": "Tipo de contrato",
        "c_emp_help": "Es el campo que más influye en la predicción. Pon 0 si no lo sabes.",
        "no_info": "sin información",
        "btn_start": "Empezar con esta oferta", "btn_reset": "Usar otra oferta",
        "m_range": "Salario/hora justo (80%)", "m_month": "Equivalente mensual",
        "m_posted": "Salario según la oferta", "m_reliab": "Confianza",
        "m_hold": "no se muestra", "m_notposted": "no indicado",
        "spinner": "Analizando los 7 puntos de condiciones laborales…",
        "rep_open": "📋 Ver el informe completo",
        "chat_hdr": "💬 Pregunta lo que quieras sobre esta oferta",
        "chat_note": "**Pregunta en cualquier idioma y te responderá en ese idioma.** Si la oferta no lo dice, te lo indicará y te dará una frase en coreano para preguntar al empleador.",
        "chat_ph": "Escribe tu pregunta",
        "chat_needkey": "Se necesita una clave API de OpenAI. Introdúcela a la izquierda.",
        "db_note": "Ofertas que ya hemos recopilado y analizado. El análisis está precalculado (sin coste); solo el chat usa la API.",
        "db_search": "Buscar empresa o título",
        "db_search_ph": "Ej.: cuidados, seguridad, fábrica",
        "db_gu": "Distrito", "db_all": "Todos", "db_scope": "Mostrar",
        "db_s1": "Con preguntas listas", "db_s2": "Con análisis", "db_s3": "Todas",
        "db_sel": "Elige una oferta (primeras 300)",
        "db_none": "Ninguna oferta coincide. Amplía el filtro.",
        "db_orig": "Texto original de la oferta", "db_qonly": "Ver solo las preguntas, en grande",
        "db_count": "ofertas",
    },
}

# 예시 질문 버튼. 각 언어로 자기 말이 나와야 누를 수 있다.
SUGGEST: dict[str, list[str]] = {
    "ko": ["이 공고 뭐라고 써있어?", "임금이 적정한가요?",
           "기숙사비를 월급에서 빼나요?", "사장님께 뭘 물어봐야 해요?"],
    "en": ["What does this posting actually say?", "Is the pay fair?",
           "Is the dormitory cost taken out of my wage?",
           "What should I ask the employer?"],
    "zh": ["这个公告写的什么？", "工资合理吗？",
           "宿舍费会从工资里扣吗？", "我该问雇主什么？"],
    "vi": ["Tin này viết những gì?", "Mức lương có hợp lý không?",
           "Tiền ký túc xá có bị trừ vào lương không?",
           "Tôi nên hỏi chủ doanh nghiệp điều gì?"],
    "ja": ["この求人には何が書かれていますか？", "賃金は適正ですか？",
           "寮費は給料から引かれますか？", "社長に何を聞けばいいですか？"],
    "es": ["¿Qué dice realmente esta oferta?", "¿El salario es justo?",
           "¿Descuentan el alojamiento del salario?",
           "¿Qué debería preguntar al empleador?"],
}


def a(lang: str, key: str) -> str:
    """앱 화면 문구. 없는 언어·키는 한국어로 대체."""
    return APP.get(lang, APP["ko"]).get(key) or APP["ko"].get(key, key)


def suggest(lang: str) -> list[str]:
    return SUGGEST.get(lang, SUGGEST["ko"])


# ─────────────────────────────────────────────────────────────────────────────
# 데이터 값의 표시 라벨
# ─────────────────────────────────────────────────────────────────────────────
#
# 모델의 학습 범주값은 그대로 두고 화면 표시만 바꾼다. 값을 번역하면 예측이 깨진다.
# 값 종류가 적고 사용자가 반드시 골라야 하는 것만 다룬다
# (industry 562개 · job_category 951개는 원값을 그대로 보여준다).

# 직종 대분류. 화면에 '1.0' 같은 코드가 뜨면 사용자가 무엇을 고르는지 알 수 없다.
KSCO: dict[str, dict[str, str]] = {
    "ko": {"1.0": "관리자", "2.0": "전문가·관련직", "3.0": "사무직",
           "4.0": "서비스직", "5.0": "판매직", "6.0": "농림어업 숙련직",
           "7.0": "기능원·관련 기능직", "8.0": "장치·기계 조작·조립직",
           "9.0": "단순노무직"},
    "en": {"1.0": "Managers", "2.0": "Professionals", "3.0": "Clerical",
           "4.0": "Service", "5.0": "Sales", "6.0": "Agriculture / fishery",
           "7.0": "Craft & trades", "8.0": "Machine operators & assemblers",
           "9.0": "Elementary occupations"},
    "zh": {"1.0": "管理人员", "2.0": "专业人员及相关职", "3.0": "办事人员",
           "4.0": "服务人员", "5.0": "销售人员", "6.0": "农林渔业熟练工",
           "7.0": "技术工及相关技能工", "8.0": "装置·机械操作及组装工",
           "9.0": "简单劳务工"},
    "vi": {"1.0": "Quản lý", "2.0": "Chuyên môn và liên quan", "3.0": "Văn phòng",
           "4.0": "Dịch vụ", "5.0": "Bán hàng", "6.0": "Nông lâm thủy sản",
           "7.0": "Thợ kỹ thuật", "8.0": "Vận hành máy và lắp ráp",
           "9.0": "Lao động giản đơn"},
    "ja": {"1.0": "管理職", "2.0": "専門職・関連職", "3.0": "事務職",
           "4.0": "サービス職", "5.0": "販売職", "6.0": "農林漁業熟練職",
           "7.0": "技能工・関連職", "8.0": "装置・機械操作および組立職",
           "9.0": "単純労務職"},
    "es": {"1.0": "Directivos", "2.0": "Profesionales", "3.0": "Administrativos",
           "4.0": "Servicios", "5.0": "Ventas", "6.0": "Agricultura y pesca",
           "7.0": "Oficios y artesanía", "8.0": "Operarios de máquinas y montaje",
           "9.0": "Ocupaciones elementales"},
}

# 기업 규모
SIZE: dict[str, dict[str, str]] = {
    "ko": {"5인미만": "5인 미만", "5-29인": "5~29인", "30-99인": "30~99인",
           "100-299인": "100~299인", "300인이상": "300인 이상"},
    "en": {"5인미만": "under 5", "5-29인": "5–29", "30-99인": "30–99",
           "100-299인": "100–299", "300인이상": "300+"},
    "zh": {"5인미만": "不足5人", "5-29인": "5~29人", "30-99인": "30~99人",
           "100-299인": "100~299人", "300인이상": "300人以上"},
    "vi": {"5인미만": "dưới 5 người", "5-29인": "5~29 người", "30-99인": "30~99 người",
           "100-299인": "100~299 người", "300인이상": "trên 300 người"},
    "ja": {"5인미만": "5人未満", "5-29인": "5~29人", "30-99인": "30~99人",
           "100-299인": "100~299人", "300인이상": "300人以上"},
    "es": {"5인미만": "menos de 5", "5-29인": "5–29", "30-99인": "30–99",
           "100-299인": "100–299", "300인이상": "más de 300"},
}

# '만' 단위는 한국·중국·일본에만 있다. 그 밖의 언어는 만 단위로 줄여 쓰면
# 읽을 수 없으므로(예: es 에서 '226만' -> '2260.000' 같은 오표기) 전체 금액을 쓴다.
MAN_UNIT: dict[str, str] = {"ko": "만원", "zh": "万韩元", "ja": "万ウォン"}


def unit_label(lang: str, unit: str) -> str:
    """입력칸 단위 표기를 화면 언어로 바꾼다.

    '만원' 을 그대로 두면 중국어 화면에 '金额 (만원)' 처럼 한국어가 섞인다.
    '만' 개념이 없는 언어(en·vi·es)는 만 단위 자체를 쓸 수 없으므로
    '만원' 을 '10,000 KRW' 처럼 배수로 풀어 적는다.
    """
    if unit != "만원":
        return WON_UNIT.get(lang, "원").strip()
    if lang in MAN_UNIT:
        return MAN_UNIT[lang]
    return "×10,000" + WON_UNIT.get(lang, " KRW")
WON_UNIT: dict[str, str] = {
    "ko": "원", "zh": "韩元", "ja": "ウォン",
    "en": " KRW", "vi": " won", "es": " wones",
}
# 천단위 구분자. 스페인어·베트남어는 점을 쓴다.
THOUSAND: dict[str, str] = {"es": ".", "vi": "."}


def value_label(lang: str, field: str, v: str) -> str:
    """선택지 표시 문구. 매핑이 없으면 원값을 그대로 돌려준다."""
    if v == "정보없음":
        return a(lang, "no_info")
    tbl = {"ksco_code": KSCO, "기업규모구간": SIZE}.get(field)
    if not tbl:
        return v
    return tbl.get(lang, tbl["ko"]).get(v, v)


def _group(lang: str, v: float) -> str:
    s = f"{v:,.0f}"
    sep = THOUSAND.get(lang)
    return s.replace(",", sep) if sep else s


def won(lang: str, v: float) -> str:
    """원 단위 금액. 언어별 구분자·단위를 붙인다."""
    return _group(lang, v) + WON_UNIT.get(lang, WON_UNIT["ko"])


def man(lang: str, hourly: float) -> str:
    """시급 -> 월 환산 표기 (월 소정근로시간 209h 기준).

    '만' 단위가 있는 언어는 만 단위로 줄이고, 없는 언어는 전체 금액을 쓴다.
    """
    monthly = hourly * 209
    if lang in MAN_UNIT:
        return f"{round(monthly / 10000)}{MAN_UNIT[lang]}"
    return won(lang, round(monthly, -3))


def man_range(lang: str, lo: float, hi: float) -> str:
    """월 환산 구간. 단위를 뒤에 한 번만 붙인다."""
    if lang in MAN_UNIT:
        return (f"{round(lo * 209 / 10000)} ~ "
                f"{round(hi * 209 / 10000)}{MAN_UNIT[lang]}")
    return (f"{_group(lang, round(lo * 209, -3))} ~ "
            f"{won(lang, round(hi * 209, -3))}")


# 신뢰도 등급값. 한국어 값('보통')이 중국어 화면에 그대로 뜨면 읽을 수 없다.
RELIABILITY: dict[str, dict[str, str]] = {
    "ko": {"높음": "높음", "보통": "보통", "낮음": "낮음", "매우낮음": "매우 낮음"},
    "en": {"높음": "High", "보통": "Medium", "낮음": "Low", "매우낮음": "Very low"},
    "zh": {"높음": "高", "보통": "中等", "낮음": "低", "매우낮음": "很低"},
    "vi": {"높음": "Cao", "보통": "Trung bình", "낮음": "Thấp", "매우낮음": "Rất thấp"},
    "ja": {"높음": "高い", "보통": "普通", "낮음": "低い", "매우낮음": "非常に低い"},
    "es": {"높음": "Alta", "보통": "Media", "낮음": "Baja", "매우낮음": "Muy baja"},
}


def reliability(lang: str, v: str) -> str:
    return RELIABILITY.get(lang, RELIABILITY["ko"]).get(v, v)
