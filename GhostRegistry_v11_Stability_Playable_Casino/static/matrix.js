let canvas = document.getElementById("matrix-canvas");

if (!canvas) {
    canvas = document.createElement("canvas");
    canvas.id = "matrix-canvas";
    document.body.appendChild(canvas);
}

const ctx = canvas.getContext("2d");

function resizeCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
}

resizeCanvas();
window.addEventListener("resize", resizeCanvas);

const chars = "010101010101 GHOST REGISTRY ";
const fontSize = 15;
let columns = Math.floor(window.innerWidth / fontSize);
let drops = [];

function resetDrops() {
    columns = Math.floor(window.innerWidth / fontSize);
    drops = [];

    for (let i = 0; i < columns; i++) {
        drops[i] = Math.floor(Math.random() * -100);
    }
}

resetDrops();
window.addEventListener("resize", resetDrops);

function draw() {
    ctx.fillStyle = "rgba(0, 0, 0, 0.065)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = "#00d9ff";
    ctx.font = fontSize + "px monospace";

    for (let i = 0; i < drops.length; i++) {
        const text = chars[Math.floor(Math.random() * chars.length)];

        ctx.fillText(text, i * fontSize, drops[i] * fontSize);

        if (drops[i] * fontSize > canvas.height && Math.random() > 0.982) {
            drops[i] = Math.floor(Math.random() * -40);
        }

        drops[i]++;
    }
}

setInterval(draw, 33);
// Live session checker: kicks locked-out, deleted, or session-reset accounts to login without manual refresh.
(function(){
  if (location.pathname === '/' || location.pathname === '/login') return;
  async function checkGhostSession(){
    try{
      const r = await fetch('/session-status', {cache:'no-store'});
      const data = await r.json();
      if(!data.ok){ window.location.href = data.redirect || '/login'; }
    }catch(e){}
  }
  setInterval(checkGhostSession, 2000);
})();
