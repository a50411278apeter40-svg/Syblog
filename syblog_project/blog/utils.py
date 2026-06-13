# 악성/성인 키워드 필터
FORBIDDEN_WORDS = [
    # 욕설
    '씨발', '시발', '개새끼', '병신', '지랄', '존나', '좆', '니미', '엿먹', '꺼져',
    '개소리', '미친놈', '미친년', '새끼', '자식', '썅', '개년', '창녀', '매춘',
    # 성적 표현
    '성기', '자지', '보지', '섹스', '야동', '포르노', '강간', '윤간', '성폭행',
    'sex', 'porn', 'fuck', 'shit', 'bitch', 'asshole', 'dick', 'pussy',
    # 폭력/혐오
    '죽어', '죽여', '자살해', '폭탄', '테러', '살인',
]

def contains_forbidden_words(text):
    if not text:
        return False
    text_lower = text.lower()
    for word in FORBIDDEN_WORDS:
        if word.lower() in text_lower:
            return True
    return False

def filter_content(text):
    """Returns (is_clean, filtered_text)"""
    if not text:
        return True, text
    text_lower = text.lower()
    for word in FORBIDDEN_WORDS:
        if word.lower() in text_lower:
            return False, text
    return True, text
