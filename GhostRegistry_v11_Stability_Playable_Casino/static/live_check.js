// Lightweight live session checker: supports lockdown and instant kick-outs without waiting for refresh.
(function(){
  async function checkSession(){
    try{
      const res = await fetch('/session-status', {cache:'no-store'});
      const data = await res.json();
      if(!data.ok){ window.location.href = '/login'; }
      if(data.force_logout){ window.location.href = '/logout'; }
    }catch(e){}
  }
  setInterval(checkSession, 2000);
})();
