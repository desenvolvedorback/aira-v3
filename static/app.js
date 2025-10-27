document.addEventListener('DOMContentLoaded', ()=>{
  const form = document.getElementById('askForm')
  const chat = document.getElementById('chat')
  const qInput = document.getElementById('question')

  function addMessage(text, cls='bot'){
    const d = document.createElement('div')
    d.className = 'msg ' + cls
    d.textContent = text
    chat.appendChild(d)
    chat.scrollTop = chat.scrollHeight
  }

  form.addEventListener('submit', async (e)=>{
    e.preventDefault()
    const q = qInput.value.trim()
    if(!q) return
    addMessage('Você: ' + q, 'user')
    qInput.value = ''
    addMessage('Airá está pensando...')
    try{
      const res = await fetch('/ask', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question:q})})
      const data = await res.json()
      if(data.error) addMessage('Erro: '+data.error)
      else addMessage('Airá: ' + data.answer)
    }catch(err){
      addMessage('Erro ao conectar com o servidor')
      console.error(err)
    }
  })
})
