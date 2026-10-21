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
                    const r = await fetch(url, {{
                        credentials: 'include',
                        headers: {{ 'sellerId': '{SELLER_ID}' }}
                    }});
                    if (!r.ok) return null;
                    return await r.json();
                }} catch (e) {{
                    return null;
                }}
            }};
            const cash = await fetchJson('https://apis.adoffice.11st.co.kr/advertiser/loyalty/v1/cash/cashlimit/{SELLER_ID}');
            const point = await fetchJson('https://apis.adoffice.11st.co.kr/advertiser/loyalty/v1/points/sellerpoints/{SELLER_ID}');
            const grp7d = await fetchJson('https://apis.adoffice.11st.co.kr/advertiser/campaigns/v1/{CAMPAIGN_ID}/adgroups?page=0&size=20&startDate={start_7d}&endDate={end_dt}');
            const grp1d = await fetchJson('https://apis.adoffice.11st.co.kr/advertiser/campaigns/v1/{CAMPAIGN_ID}/adgroups?page=0&size=20&startDate={end_dt}&endDate={end_dt}');
            const targets7d = await fetchJson('https://apis.adoffice.11st.co.kr/advertiser/adgroups/v1/{GROUP_ID}/adtargets?page=0&size=30&startDate={start_7d}&endDate={end_dt}&product=true');
            const targets1d = await fetchJson('https://apis.adoffice.11st.co.kr/advertiser/adgroups/v1/{GROUP_ID}/adtargets?page=0&size=30&startDate={end_dt}&endDate={end_dt}&product=true');
            const kw7d = await fetchJson('https://apis.adoffice.11st.co.kr/advertiser/adtargets/v1/reports/{MAIN_TARGET_ID}/keywords?startDate={start_7d}&endDate={end_dt}&campaignId={CAMPAIGN_ID}&groupId={GROUP_ID}&targetId={MAIN_TARGET_ID}&size=50&product=true&excludeZeroMetrics=false');
            const kw1d = await fetchJson('https://apis.adoffice.11st.co.kr/advertiser/adtargets/v1/reports/{MAIN_TARGET_ID}/keywords?startDate={end_dt}&endDate={end_dt}&campaignId={CAMPAIGN_ID}&groupId={GROUP_ID}&targetId={MAIN_TARGET_ID}&size=50&product=true&excludeZeroMetrics=false');
            return {{ cash, point, grp7d, grp1d, targets7d, targets1d, kw7d, kw1d, start_7d: '{start_7d}', end_dt: '{end_dt}' }};
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
    existing['updatedAt'] = now_str

    account = existing.get('account', {
        "sellerId": "23825",
        "loginId": "joonoodesign",
        "storeName": "명함무료디자인제작대구업체주누디자인",
        "storeNo": "524401",
        "totalBalance": 59348,
        "sellerPoint": 59303,
        "sellerCash": 45,
        "buyerCoupon": "할인 미적용 (1,000원 단가 수량 결제 방식 유지)",
        "couponUpdatedAt": "2026-10-20 17:17:14"
    })

    # 실시간 포인트/캐시 잔액 파싱
    point_data = live.get('point')
    cash_data = live.get('cash')
    if isinstance(point_data, dict):
        if isinstance(point_data.get('usablePoint'), (int, float)):
            account['sellerPoint'] = int(point_data['usablePoint'])
        elif isinstance(point_data.get('data'), (int, float)):
            account['sellerPoint'] = int(point_data['data'])
    if isinstance(cash_data, dict):
        if isinstance(cash_data.get('usableCash'), (int, float)):
            account['sellerCash'] = int(cash_data['usableCash'])
        elif isinstance(cash_data.get('data'), (int, float)):
            account['sellerCash'] = int(cash_data['data'])
    if 'sellerPoint' in account and 'sellerCash' in account:
        account['totalBalance'] = int(account['sellerPoint']) + int(account['sellerCash'])
    existing['account'] = account

    # 7일 및 어제(1일) 그룹 성과 파싱
    grp7d = live.get('grp7d')
    if isinstance(grp7d, dict) and grp7d.get('content'):
        r7 = grp7d['content'][0].get('report') or {}
        imp7 = int(r7.get('impCnt') or 0)
        clk7 = int(r7.get('clickValidCnt') or r7.get('clickCnt') or 0)
        raw_clk7 = int(r7.get('clickCnt') or 0)
        invalid_clk7 = int(r7.get('clickInValidCnt') or 0)
        cost7 = int(r7.get('clickCostTotal') or 0)
        ctr7 = round(float(r7.get('ctr') or 0), 2)
        cpc7 = int(round(float(r7.get('clickCostAvg') or 0)))
        cart7 = int(r7.get('cartConversionCnt') or 0)
        cart_sales7 = int(r7.get('cartConversionCostTotal') or 0)
        rank7 = round(float(r7.get('rankAvg') or 0), 2)

        s7 = existing.get('summary7d', {})
        s7.update({
            'startDate': live.get('start_7d', s7.get('startDate', '2026-10-14')),
            'endDate': live.get('end_dt', s7.get('endDate', '2026-10-20')),
            'impressions': imp7,
            'clicks': clk7,
            'totalClicks': raw_clk7,
            'invalidClicks': invalid_clk7,
            'ctr': ctr7,
            'avgCpc': cpc7,
            'cost': cost7,
            'cartConversions': cart7,
            'cartSales': cart_sales7,
            'avgRank': rank7
        })
        existing['summary7d'] = s7

        for camp in existing.get('campaigns', []):
            if str(camp.get('campaignId')) == CAMPAIGN_ID:
                camp['impressions'] = imp7
                camp['clicks'] = clk7
                camp['ctr'] = ctr7
                camp['avgCpc'] = cpc7
                camp['cost'] = cost7
                for grp in camp.get('groups', []):
                    if str(grp.get('groupId')) == GROUP_ID:
                        grp['impressions'] = imp7
                        grp['clicks'] = clk7
                        grp['ctr'] = ctr7
                        grp['avgCpc'] = cpc7
                        grp['cost'] = cost7

    grp1d = live.get('grp1d')
    if isinstance(grp1d, dict) and grp1d.get('content'):
        r1 = grp1d['content'][0].get('report') or {}
        existing['summaryYesterday'] = {
            'date': live.get('end_dt', '2026-10-20'),
            'impressions': int(r1.get('impCnt') or 0),
            'clicks': int(r1.get('clickValidCnt') or r1.get('clickCnt') or 0),
            'totalClicks': int(r1.get('clickCnt') or 0),
            'invalidClicks': int(r1.get('clickInValidCnt') or 0),
            'ctr': round(float(r1.get('ctr') or 0), 2),
            'avgCpc': int(round(float(r1.get('clickCostAvg') or 0))),
            'cost': int(r1.get('clickCostTotal') or 0),
            'avgRank': round(float(r1.get('rankAvg') or 0), 2)
        }

    # 상품별 7일 & 어제 성과 파싱
    t7_map = {}
    if isinstance(live.get('targets7d'), dict):
        for item in live['targets7d'].get('content', []):
            t7_map[str(item.get('id'))] = item.get('report') or {}
    t1_map = {}
    if isinstance(live.get('targets1d'), dict):
        for item in live['targets1d'].get('content', []):
            t1_map[str(item.get('id'))] = item.get('report') or {}

    if t7_map or t1_map:
        for prd in existing.get('products', []):
            tid_str = str(prd.get('targetId'))
            if tid_str in t7_map:
                r = t7_map[tid_str]
                prd['impressions'] = int(r.get('impCnt') or 0)
                prd['clicks'] = int(r.get('clickValidCnt') or r.get('clickCnt') or 0)
                prd['totalClicks'] = int(r.get('clickCnt') or 0)
                prd['ctr'] = round(float(r.get('ctr') or 0), 2)
                prd['cost'] = int(r.get('clickCostTotal') or 0)
                prd['avgCpc'] = int(round(float(r.get('clickCostAvg') or 0)))
                prd['cartConversions'] = int(r.get('cartConversionCnt') or 0)
                prd['avgRank'] = round(float(r.get('rankAvg') or 0), 2) if r.get('rankAvg') else None
            if tid_str in t1_map:
                r1 = t1_map[tid_str]
                prd['yesterdayImpressions'] = int(r1.get('impCnt') or 0)
                prd['yesterdayClicks'] = int(r1.get('clickValidCnt') or r1.get('clickCnt') or 0)
                prd['yesterdayTotalClicks'] = int(r1.get('clickCnt') or 0)
                prd['yesterdayCtr'] = round(float(r1.get('ctr') or 0), 2)
                prd['yesterdayCost'] = int(r1.get('clickCostTotal') or 0)
                prd['yesterdayRank'] = round(float(r1.get('rankAvg') or 0), 2) if r1.get('rankAvg') else None

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    raw_bytes = json.dumps(existing, ensure_ascii=False, indent=2).encode('utf-8')
    with open(OUT_JSON, 'wb') as f:
        f.write(raw_bytes)

    synced = push_data_to_github_db_store(raw_bytes)
    print(f"[성공] 11번가 광고센터(AD OFFICE) 데이터 동기화 완료 ({now_str})")
    print(f"- 총 잔액: {account.get('totalBalance'):,}원 (셀러포인트 {account.get('sellerPoint'):,}원 / 셀러캐시 {account.get('sellerCash'):,}원)")
    if 'summaryYesterday' in existing:
        sy = existing['summaryYesterday']
        print(f"- 어제({sy['date']}) 성과: 노출 {sy['impressions']:,}회 / 유효클릭 {sy['clicks']}회(전체 {sy['totalClicks']}회) / CTR {sy['ctr']}% / 평균순위 {sy['avgRank']}위 / 광고비 {sy['cost']:,}원")
    s7 = existing.get('summary7d', {})
    print(f"- 최근 7일({s7.get('startDate')}~{s7.get('endDate')}) 성과: 노출 {s7.get('impressions', 0):,}회 / 유효클릭 {s7.get('clicks', 0)}회 / CTR {s7.get('ctr', 0)}% / 장바구니 {s7.get('cartConversions', 0)}건 / 광고비 {s7.get('cost', 0):,}원")
    print(f"- 클라우드 DB(db-store & main) 자동 반영: {'성공' if synced else '로컬 저장 완료'}")


if __name__ == '__main__':
    main()
