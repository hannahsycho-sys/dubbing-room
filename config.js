/* ============================================================
 *  config.js — 딱 두 줄만 채우면 됩니다
 *
 *  Supabase 에서 복사해 오는 값입니다.
 *  (Supabase 대시보드 → 프로젝트 → Settings → API)
 *
 *  anon key 는 공개되어도 되는 키입니다. RLS 정책으로 보호됩니다.
 *  (schema.sql 을 실행하면 정책이 같이 만들어집니다)
 * ============================================================ */

const CONFIG = {
  SUPABASE_URL: "https://sqcmfyepodtqznunidde.supabase.co",       // 예) "https://abcdefgh.supabase.co"
  SUPABASE_ANON_KEY: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNxY21meWVwb2R0cXpudW5pZGRlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY3MDkxMTMsImV4cCI6MjEwMjI4NTExM30.7VuFaymkE6M_OXUuHngGF_2Rzy_nTY6jnzzELBa2bnM",  // 예) "eyJhbGciOi..."

  BUCKET: "takes",        // 녹음이 쌓일 스토리지 버킷 이름 (바꾸지 않아도 됩니다)

  /* 관리자 화면 주소 뒤에 붙이는 암호.
     https://내주소/collab/?admin=바꿔주세요  로 들어가면 전체 현황이 보입니다.
     학생에게 알려주지 마세요. */
  ADMIN_KEY: "헤이즐",
};
