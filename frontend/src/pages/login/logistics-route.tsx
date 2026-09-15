const particles = [0, 1, 2];

export function LogisticsRoute() {
  return <div className="county-login__route" data-login-route-layer data-route-placement="city-corridor" aria-hidden="true">
    <svg viewBox="0 0 1000 620" preserveAspectRatio="xMidYMid slice">
      <defs>
        <filter id="login-route-glow" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <path id="login-route-path" d="M72 510 C180 430 270 490 358 402 S505 330 592 360 S730 300 816 215 S916 190 982 120" />
      </defs>
      <use href="#login-route-path" className="county-login__route-shadow" />
      <use href="#login-route-path" className="county-login__route-line" />
      <use href="#login-route-path" className="county-login__route-energy" />
      {particles.map((particle) => <circle key={particle} r="3.5" className="county-login__route-particle" data-login-particle>
        <animateMotion dur={`${8.5 + particle * .35}s`} begin={`${particle * -1.35}s`} repeatCount="indefinite">
          <mpath href="#login-route-path" />
        </animateMotion>
      </circle>)}
    </svg>
    <span className="county-login__pin county-login__pin--county"><i />县城枢纽</span>
    <span className="county-login__pin county-login__pin--town"><i />乡镇驿站</span>
    <span className="county-login__pin county-login__pin--station"><i />配送站</span>
  </div>;
}
