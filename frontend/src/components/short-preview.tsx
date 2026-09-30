type Props = { variant?: "video" | "product" };

/** Illustrative layout only, not a rendered customer video. */
export function ShortPreview({ variant = "video" }: Props) {
  return (
    <div className={`short-illustration ${variant}`} aria-hidden="true">
      <div className="illustration-top"><span>cutpick.</span><span>9:16</span></div>
      {variant === "video" ? (
        <>
          <div className="landscape-sun" /><div className="landscape-ridge ridge-back" /><div className="landscape-ridge ridge-front" />
          <div className="illustration-caption"><small>나만 알고 싶은 순간</small><strong>긴 이야기 속,<br /><em>빛나는 한 장면.</em></strong></div>
        </>
      ) : (
        <>
          <div className="product-orbit" /><div className="sample-bottle"><span>DAILY<br />PICK</span></div>
          <div className="illustration-caption"><small>일상을 바꾸는 작은 선택</small><strong>매일 함께하는<br /><em>나의 새로운 픽.</em></strong></div>
        </>
      )}
      <div className="illustration-bottom"><span>디자인 예시</span><span>▶ ━━━━━</span></div>
    </div>
  );
}
