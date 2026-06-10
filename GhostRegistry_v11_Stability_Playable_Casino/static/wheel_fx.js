// GhostRegistry wheel effects: fast start, slow landing, particles, reward reveal.
document.querySelectorAll('.spin-form').forEach(form => {
  form.addEventListener('submit', ev => {
    const wheel = document.getElementById(form.dataset.wheel);
    const btn = form.querySelector('button');
    if(!wheel || !btn) return;
    ev.preventDefault();
    btn.disabled = true;
    btn.textContent = 'Spinning...';
    wheel.classList.remove('landed');
    wheel.classList.add('spinning-now');
    document.body.classList.add('wheel-shake-soft');
    setTimeout(() => { form.submit(); }, 4200);
  });
});
setTimeout(()=>document.body.classList.remove('wheel-shake-soft'), 5000);
