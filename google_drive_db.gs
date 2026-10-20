/**
 * ============================================================================
 * [11번가 광고 효율 분석 & 최적화 대시보드] 구글 드라이브 DB & 24시간 클라우드 동기화 브릿지
 * ============================================================================
 *
 * ★ 이 스크립트가 하는 일:
 * 1. 내 구글 드라이브 안에 '11st_ad_optimizer_db.json' 파일을 자동 생성하여
 *    11번가 포커스클릭 캠페인/그룹 입찰가, 상품별 SEO 상품명·검색태그(20개),
 *    제외키워드(Negative Keywords), 구매자 쿠폰 설정 및 7일/30일 성과 리포트를 안전하게 저장합니다.
 * 2. 내 컴퓨터를 꺼놓아도 아이폰·아이패드·PC 어디서나 24시간 실시간으로 동일한 데이터를
 *    열람하고 수정 내용을 즉시 동기화할 수 있습니다.
 *
 * ★ 1분 설치 방법:
 * 1. https://script.google.com 접속 -> [새 프로젝트] 클릭
 * 2. 기존 코드를 지우고 이 코드 전체를 붙여넣은 뒤 저장(Ctrl + S)
 * 3. 우측 상단 [배포] -> [새 배포] 클릭 -> 유형: [웹 앱] 선택
 *    - 다음 사용자로 실행: "나 (본인 구글 계정)"
 *    - 액세스 권한이 있는 사용자: "모든 사용자 (Anyone)"
 * 4. 배포 후 생성된 '웹 앱 URL (https://script.google.com/macros/s/.../exec)'을
 *    웹페이지 상단 [클라우드 DB 연동 설정] 창에 붙여넣으면 완료!
 */

const DB_FILE_NAME = '11st_ad_optimizer_db.json';

function getOrCreateDbFile() {
  const files = DriveApp.getFilesByName(DB_FILE_NAME);
  if (files.hasNext()) {
    return files.next();
  }
  const initialData = JSON.stringify({
    updatedAt: new Date().toISOString(),
    account: {
      sellerId: '23825',
      loginId: 'joonoodesign',
      storeName: '명함무료디자인제작대구업체주누디자인',
      storeNo: '524401'
    }
  });
  return DriveApp.createFile(DB_FILE_NAME, initialData, MimeType.PLAIN_TEXT);
}

function doGet(e) {
  try {
    const file = getOrCreateDbFile();
    const content = file.getBlob().getDataAsString('UTF-8') || '{"updatedAt":0}';
    return ContentService
      .createTextOutput(content)
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doPost(e) {
  try {
    const rawBody = e.postData && e.postData.contents ? e.postData.contents : '{}';
    const parsed = JSON.parse(rawBody);

    // 1) 외부 API 프록시 요청이 필요한 경우 (선택적 브릿지 기능)
    if (parsed && parsed.action === 'elevenstApiProxy' && parsed.targetUrl) {
      const resp = UrlFetchApp.fetch(parsed.targetUrl, {
        method: parsed.method || 'GET',
        headers: parsed.headers || {},
        payload: parsed.payload ? JSON.stringify(parsed.payload) : undefined,
        muteHttpExceptions: true
      });
      const status = resp.getResponseCode();
      const text = resp.getContentText('UTF-8');
      let data = null;
      try {
        data = JSON.parse(text);
      } catch (err) {
        data = text;
      }
      return ContentService
        .createTextOutput(JSON.stringify({ ok: status >= 200 && status < 300, status: status, data: data }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // 2) 일반 DB 저장 요청인 경우 ('11st_ad_optimizer_db.json' 전체 갱신)
    const file = getOrCreateDbFile();
    file.setContent(rawBody);
    return ContentService
      .createTextOutput(JSON.stringify({ ok: true, fileName: DB_FILE_NAME, savedAt: Date.now() }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
