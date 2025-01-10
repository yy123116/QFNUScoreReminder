import requests
from PIL import Image
from io import BytesIO
from bs4 import BeautifulSoup
from captcha_ocr import get_ocr_res
import os
from dotenv import load_dotenv
import time
import json
from dingtalk import dingtalk

load_dotenv()

DD_BOT_TOKEN = os.getenv("DD_BOT_TOKEN")
DD_BOT_SECRET = os.getenv("DD_BOT_SECRET")

# 设置基本的URL和数据
RandCodeUrl = "http://zhjw.qfnu.edu.cn/verifycode.servlet"  # 验证码请求URL
loginUrl = "http://zhjw.qfnu.edu.cn/Logon.do?method=logonLdap"  # 登录请求URL
dataStrUrl = (
    "http://zhjw.qfnu.edu.cn/Logon.do?method=logon&flag=sess"  # 初始数据请求URL
)


def get_initial_session():
    """
    创建会话并获取初始数据
    返回: (session对象, cookies字典, 初始数据字符串)
    """
    session = requests.session()
    response = session.get(dataStrUrl, timeout=1000)
    cookies = session.cookies.get_dict()
    return session, cookies, response.text


def handle_captcha(session, cookies):
    """
    获取并识别验证码
    返回: 识别出的验证码字符串
    """
    response = session.get(RandCodeUrl, cookies=cookies)

    # 添加调试信息
    if response.status_code != 200:
        print(f"请求验证码失败，状态码: {response.status_code}")
        return None

    try:
        image = Image.open(BytesIO(response.content))
    except Exception as e:
        print(f"无法识别图像文件: {e}")
        return None

    return get_ocr_res(image)


def generate_encoded_string(data_str, user_account, user_password):
    """
    生成登录所需的encoded字符串
    参数:
        data_str: 初始数据字符串
        user_account: 用户账号
        user_password: 用户密码
    返回: encoded字符串
    """
    res = data_str.split("#")
    code, sxh = res[0], res[1]
    data = f"{user_account}%%%{user_password}"
    encoded = ""
    b = 0

    for a in range(len(code)):
        if a < 20:
            encoded += data[a]
            for _ in range(int(sxh[a])):
                encoded += code[b]
                b += 1
        else:
            encoded += data[a:]
            break
    return encoded


def login(session, cookies, user_account, user_password, random_code, encoded):
    """
    执行登录操作
    返回: 登录响应结果
    """
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.116 Safari/537.36",
        "Origin": "http://zhjw.qfnu.edu.cn",
        "Referer": "http://zhjw.qfnu.edu.cn/",
        "Upgrade-Insecure-Requests": "1",
    }

    data = {
        "userAccount": user_account,
        "userPassword": user_password,
        "RANDOMCODE": random_code,
        "encoded": encoded,
    }

    return session.post(
        loginUrl, headers=headers, data=data, cookies=cookies, timeout=1000
    )


def get_user_credentials():
    """
    获取用户账号和密码
    返回: (user_account, user_password)
    """
    user_account = os.getenv("USER_ACCOUNT")
    user_password = os.getenv("USER_PASSWORD")
    print(f"用户名: {user_account}\n")
    print(f"密码: {user_password}\n")
    return user_account, user_password


def simulate_login(user_account, user_password):
    """
    模拟登录过程
    返回: (session对象, cookies字典)
    抛出:
        Exception: 当验证码错误时
    """
    session, cookies, data_str = get_initial_session()

    for attempt in range(3):  # 尝试三次
        random_code = handle_captcha(session, cookies)
        print(f"验证码: {random_code}\n")
        encoded = generate_encoded_string(data_str, user_account, user_password)
        response = login(
            session, cookies, user_account, user_password, random_code, encoded
        )

        # 检查响应状态码和内容
        if response.status_code == 200:
            if "验证码错误!!" in response.text:
                print(f"验证码识别错误，重试第 {attempt + 1} 次\n")
                continue  # 继续尝试
            if "密码错误" in response.text:
                raise Exception("用户名或密码错误")
            print("登录成功，cookies已返回\n")
            return session, cookies
        else:
            raise Exception("登录失败")

    raise Exception("验证码识别错误，请重试")


# 访问成绩页面
def get_score_page(session, cookies):
    url = "http://zhjw.qfnu.edu.cn/jsxsd/kscj/cjcx_list?kksj=2024-2025-1"
    respense = session.get(url, cookies=cookies)
    return respense.text


# 解析成绩页面
def analyze_score_page(pagehtml):
    soup = BeautifulSoup(pagehtml, "lxml")
    results = []

    # 找到成绩表格
    table = soup.find("table", {"id": "dataList"})
    if table:
        # 遍历表格的每一行
        rows = table.find_all("tr")[1:]  # 跳过表头
        for row in rows:
            columns = row.find_all("td")
            if len(columns) > 5:
                subject_name = columns[3].get_text(strip=True)
                score = columns[5].get_text(strip=True)
                results.append((subject_name, score))

    return results


# 分离新增成绩的科目和成绩
def get_new_scores(current_scores, last_scores):
    """
    获取新增的成绩
    参数:
        current_scores: 当前获取的成绩列表
        last_scores: 上一次获取的成绩列表
    返回: 新增成绩的列表
    """
    # 使用集合差集来找出新增的成绩
    new_scores = [score for score in current_scores if score not in last_scores]
    return new_scores


def test():
    global last_score_list
    with open("test.json", "r", encoding="utf-8") as f:
        testinfo = json.load(f)
        # 将字符串解析为 Python 列表
        current_scores = eval(testinfo["current_scores"])
        last_scores = eval(testinfo["last_scores"])
        print(current_scores)
        print(last_scores)
        new_scores = get_new_scores(current_scores, last_scores)
        print(new_scores)


def print_welcome():
    print("\n" * 30)
    print(f"\n{'*' * 10} 曲阜师范大学教务系统模拟登录脚本 {'*' * 10}\n")
    print("By W1ndys")
    print("https://github.com/W1ndys")
    print("\n\n")


def main():
    """
    主函数，协调整个程序的执行流程
    """

    # 定义全局变量，存储上一次的数据
    global last_score_list
    last_score_list = []  # 初始化为空列表

    print_welcome()

    # 获取环境变量
    user_account, user_password = get_user_credentials()
    if not user_account or not user_password:
        print("请在.env文件中设置USER_ACCOUNT和USER_PASSWORD环境变量\n")
        with open(".env", "w", encoding="utf-8") as f:
            f.write("USER_ACCOUNT=\nUSER_PASSWORD=")
        return

    # 模拟登录并获取会话
    session, cookies = simulate_login(user_account, user_password)

    if not session or not cookies:
        print("无法建立会话，请检查网络连接或教务系统的可用性。")
        return

    while True:

        # 访问成绩页面
        score_page = get_score_page(session, cookies)

        # 解析成绩
        score_list = analyze_score_page(score_page)

        # 初始化成绩列表
        if not last_score_list:
            print("初始化成绩列表")
            last_score_list = score_list

        # 检查是否有新成绩
        if score_list != last_score_list:
            new_scores = get_new_scores(score_list, score_list)
            print(f"发现新成绩！{new_scores}")
            dingtalk(DD_BOT_TOKEN, DD_BOT_SECRET, "发现新成绩！", f"{new_scores}")
            last_score_list = score_list  # 更新全局变量
        else:
            print(f"没有新成绩，当前成绩{score_list}")

        time.sleep(2)


if __name__ == "__main__":
    main()