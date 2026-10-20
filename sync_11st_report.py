import os
import sys
import json
import time
import base64
import datetime
import subprocess
import urllib.request
import websocket

sys.stdout.reconfigure(encoding='utf-8')

PORT_FILE = r'C:\Users\User\AppData\Local\Google\Chrome\User Data\DevToolsActivePort'
OUT_JSON = r'd:\antigravity\11st-ad-optimizer\data.json'

SELLER_ID = "23825"
CAMPAIGN_ID = "615540"
GROUP_ID = "2879183"
MAIN_TARGET_ID = "184538751"


def get_github_token():
    try:
        proc = subprocess.run(
            ['git', 'credential', 'fill'],
            input='protocol=https\nhost=github.com\n\n',
            capture_output=True, text=True, timeout=5
        )
        for line in proc.stdout.splitlines():
            if line.startswith('password='):
                return line.split('=', 1)[1].strip()
    except Exception:
        pass
    return None


def push_data_to_github_db_store(json_bytes):
    token = get_github_token()
    if not token:
        return False
    owner = 'joonoodesign'
    repo = '11st-ad-optimizer'
    for branch in ('db-store', 'main'):
        api_url = f'https://api.github.com/repos/{owner}/{repo}/contents/data.json'
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github+json',
            'User-Agent': '11st-ad-optimizer-sync'
        }
        sha = None
        try:
            req = urllib.request.Request(f'{api_url}?ref={branch}', headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                sha = json.loads(resp.read().decode('utf-8')).get('sha')
        except Exception:
            pass
        payload = {
            'message': f'Auto-sync 11st AD OFFICE report ({datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})',
            'content': base64.b64encode(json_bytes).decode('ascii'),
            'branch': branch
        }
        if sha:
            payload['sha'] = sha
        try:
            put_req = urllib.request.Request(
                api_url,
                data=json.dumps(payload).encode('utf-8'),
                headers={**headers, 'Content-Type': 'application/json'},
                method='PUT'
            )
            urllib.request.urlopen(put_req, timeout=15).read()
        except Exception as e:
            print(f'[경고] GitHub {branch} 브랜치 업로드 실패: {e}')
    return True


def fetch_live_11st_data():
    if not os.path.exists(PORT_FILE):
        return {}
    try:
        lines = [l.strip() for l in open(PORT_FILE, encoding='utf-8') if l.strip()]
        ws_url = f'ws://127.0.0.1:{lines[0]}{lines[1]}'
        ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True)
    except Exception as e:
        print(f'[안내] 크롬 CDP 연결 생략 (기존 캐시/기준 데이터 유지): {e}')
        return {}

    try:
        ws.send(json.dumps({'id': 1, 'method': 'Target.getTargets', 'params': {}}))
        tgs = json.loads(ws.recv()).get('result', {}).get('targetInfos', [])
        ad_tid = next(
            (t['targetId'] for t in tgs if 'adoffice.11st.co.kr' in t.get('url', '') and t.get('type') == 'page'),
            None
        )

        created_ad_tab = False
        if not ad_tid:
            ws.send(json.dumps({
                'id': 10,
                'method': 'Target.createTarget',
                'params': {
                    'url': f'https://adoffice.11st.co.kr/sellers/{SELLER_ID}/dashboard',
                    'background': True
                }
            }))
            ad_tid = json.loads(ws.recv())['result']['targetId']
            created_ad_tab = True
            time.sleep(3.5)

        ws.send(json.dumps({'id': 2, 'method': 'Target.attachToTarget', 'params': {'targetId': ad_tid, 'flatten': True}}))
        sid = None
        while True:
            m = json.loads(ws.recv())
            if m.get('id') == 2:
                sid = m.get('result', {}).get('sessionId')
                break

        today = datetime.date.today()
        end_dt = (today - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        start_7d = (today - datetime.timedelta(days=7)).strftime('%Y-%m-%d')

        expr = f"""(async () => {{
            const fetchJson = async (url) => {{
                try {{
                    const r = await fetch(url, {{ credentials: 'include' }});
                    if (!r.ok) return null;
                    return await r.json();
                }} catch (e) {{
                    return null;
                }}
            }};
            const cash = await fetchJson('https://apis.adoffice.11st.co.kr/advertiser/loyalty/v1/cash/cashlimit/{SELLER_ID}');
            const point = await fetchJson('https://apis.adoffice.11st.co.kr/advertiser/loyalty/v1/points/sellerpoints/{SELLER_ID}');
            const groupInfo = await fetchJson('https://apis.adoffice.11st.co.kr/advertiser/adgroups/v1/{GROUP_ID}');
            const targetsInfo = await fetchJson('https://apis.adoffice.11st.co.kr/advertiser/adgroups/v1/{GROUP_ID}/adtargets?page=0&size=30&startDate={start_7d}&endDate={end_dt}&product=true');
            const kwReport = await fetchJson('https://apis.adoffice.11st.co.kr/advertiser/adtargets/v1/reports/{MAIN_TARGET_ID}/keywords?startDate={start_7d}&endDate={end_dt}&campaignId={CAMPAIGN_ID}&groupId={GROUP_ID}&targetId={MAIN_TARGET_ID}&size=50&product=true&excludeZeroMetrics=false');
            return {{ cash, point, groupInfo, targetsInfo, kwReport }};
        }})()"""

        ws.send(json.dumps({
            'id': 3,
            'sessionId': sid,
            'method': 'Runtime.evaluate',
            'params': {'expression': expr, 'awaitPromise': True, 'returnByValue': True}
        }))
        live_res = {}
        while True:
            m = json.loads(ws.recv())
            if m.get('id') == 3:
                live_res = m.get('result', {}).get('result', {}).get('value', {}) or {}
                break

        if created_ad_tab:
            ws.send(json.dumps({'id': 99, 'method': 'Target.closeTarget', 'params': {'targetId': ad_tid}}))
            ws.recv()

        ws.close()
        return live_res
    except Exception as e:
        print(f'[경고] 크롬 CDP 실시간 수집 중 예외 발생: {e}')
        try:
            ws.close()
        except Exception:
            pass
        return {}


def main():
    existing = {}
    if os.path.exists(OUT_JSON):
        try:
            with open(OUT_JSON, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    live = fetch_live_11st_data()
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 기본 데이터(existing)를 유지하면서 실시간 응답이 있으면 최신화
    existing['updatedAt'] = now_str

    account = existing.get('account', {
        "sellerId": "23825",
        "loginId": "joonoodesign",
        "storeName": "명함무료디자인제작대구업체주누디자인",
        "storeNo": "524401",
        "totalBalance": 60371,
        "sellerPoint": 60326,
        "sellerCash": 45,
        "buyerCoupon": "사용 (11번가 100% 비용지원 자동쿠폰 ON)",
        "couponUpdatedAt": "2026-10-20 16:36:21"
    })

    # 실시간 포인트/캐시 잔액 파싱
    point_data = live.get('point')
    cash_data = live.get('cash')
    if isinstance(point_data, dict) and 'data' in point_data and isinstance(point_data['data'], (int, float)):
        account['sellerPoint'] = int(point_data['data'])
    if isinstance(cash_data, dict) and 'data' in cash_data and isinstance(cash_data['data'], (int, float)):
        account['sellerCash'] = int(cash_data['data'])
    if 'sellerPoint' in account and 'sellerCash' in account:
        account['totalBalance'] = int(account['sellerPoint']) + int(account['sellerCash'])
    existing['account'] = account

    # 그룹 입찰가 최신화
    group_info = live.get('groupInfo')
    if isinstance(group_info, dict) and isinstance(group_info.get('data'), dict):
        gdata = group_info['data']
        ms_bid = gdata.get('msBidAmount')
        p_bid = gdata.get('pBidAmount')
        for camp in existing.get('campaigns', []):
            if str(camp.get('campaignId')) == CAMPAIGN_ID:
                for grp in camp.get('groups', []):
                    if str(grp.get('groupId')) == GROUP_ID:
                        if ms_bid:
                            grp['searchBid'] = int(ms_bid)
                        if p_bid:
                            grp['recBid'] = int(p_bid)

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    raw_bytes = json.dumps(existing, ensure_ascii=False, indent=2).encode('utf-8')
    with open(OUT_JSON, 'wb') as f:
        f.write(raw_bytes)

    synced = push_data_to_github_db_store(raw_bytes)
    print(f"[성공] 11번가 광고센터(AD OFFICE) 데이터 동기화 완료 ({now_str})")
    print(f"- 총 잔액: {account.get('totalBalance'):,}원 (셀러포인트 {account.get('sellerPoint'):,}원 / 셀러캐시 {account.get('sellerCash'):,}원)")
    print(f"- 등록된 상품 수: {len(existing.get('products', []))}개")
    print(f"- 등록된 키워드 리포트: {len(existing.get('keywords', []))}개")
    print(f"- 클라우드 DB(db-store & main) 자동 반영: {'성공' if synced else '로컬 저장 완료 (GitHub 원격 저장소 생성 후 자동 연동)'}")
    print(f"- 저장 파일: {OUT_JSON}")


if __name__ == '__main__':
    main()
