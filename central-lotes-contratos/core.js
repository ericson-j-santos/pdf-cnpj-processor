/* Regras puras, testáveis também fora do navegador. Sem rede e sem efeitos externos. */
const LotesCore = (() => {
  const ETAPAS = ['Entrada', 'Preflight somente leitura', 'Download', 'Conferência', 'Upload interno', 'Publicação', 'Validação independente', 'Replay seguro', 'Encerramento'];
  const TIPOS = ['FATO_INFORMADO','FALHA_VALIDACAO','ERRO_TRANSITORIO','ERRO_DEFINITIVO','ACAO_HUMANA','DIAGNOSTICO_SEM_EFEITO','ACAO_EFETIVA_INFORMADA'];
  const TIPO_LABEL = {
    FATO_INFORMADO:'Fato informado, não verificado', FALHA_VALIDACAO:'Falha de validação', ERRO_TRANSITORIO:'Erro transitório', ERRO_DEFINITIVO:'Erro definitivo', ACAO_HUMANA:'Depende de ação humana', DIAGNOSTICO_SEM_EFEITO:'Diagnóstico sem efeito', ACAO_EFETIVA_INFORMADA:'Ação efetiva informada'
  };
  const MAX_INTERVALO = 10000;
  const MAX_ENTRADAS = 1000;
  const SHA_RE = /^[a-f0-9]{64}$/i;
  const texto = (x, max=160) => String(x ?? '').trim().slice(0,max);
  const uuid = () => (globalThis.crypto && crypto.randomUUID) ? crypto.randomUUID() : 'id-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
  const chave = ({inicio, fim, origem, destino}) => ['contratos-v1', inicio, fim, texto(origem).toLowerCase(), texto(destino).toLowerCase()].join('|');
  function normalizarLote(form, lotes) {
    const inicio = Number(form.inicio), fim = Number(form.fim), max = Number(form.limite ?? 250);
    if (!Number.isSafeInteger(inicio) || !Number.isSafeInteger(fim) || inicio < 1 || fim < inicio || fim - inicio + 1 > MAX_INTERVALO) throw Error('Intervalo inválido ou maior que 10.000 contratos.');
    if (!Number.isSafeInteger(max) || max < 1 || max > 1000) throw Error('O limite por lote deve ficar entre 1 e 1.000.');
    if (fim - inicio + 1 > max) throw Error(`Intervalo com ${fim-inicio+1} contratos excede limite configurado (${max}).`);
    const origem = texto(form.origem,200), destino = texto(form.destino,200), responsavel = texto(form.responsavel,100);
    if (!origem || !destino || !responsavel) throw Error('Origem, destino e responsável são obrigatórios.');
    if (lotes.some(l => l.status !== 'ARQUIVADO' && !(fim < l.inicio || inicio > l.fim))) throw Error('Sobreposição com outro lote ativo: bloqueado para evitar duplicação.');
    if (lotes.length >= MAX_ENTRADAS) throw Error('Limite do painel atingido. Exporte e arquive o histórico antes de ampliar.');
    const agora = new Date().toISOString();
    return {id:uuid(),inicio,fim,origem,destino,responsavel,chave:chave({inicio,fim,origem,destino}),estado:'RASCUNHO',etapa:0,informadosSucesso:0,informadosFalha:0,tentativas:0,checksum:'',checkpoint:'',evidencias:[],criadoEm:agora,atualizadoEm:agora};
  }
  function atualizarQuantidades(lote, campos) {
    const total = lote.fim-lote.inicio+1;
    const sucesso = Number(campos.sucesso), falha = Number(campos.falha), tentativas=Number(campos.tentativas);
    if (![sucesso,falha,tentativas].every(n=>Number.isSafeInteger(n)&&n>=0)) throw Error('Quantidades e tentativas precisam ser inteiros não negativos.');
    if (sucesso+falha > total) throw Error('Sucessos + falhas excedem a quantidade do lote.');
    if (tentativas > 99999) throw Error('Quantidade de tentativas fora do limite.');
    return {...lote,informadosSucesso:sucesso,informadosFalha:falha,tentativas,atualizadoEm:new Date().toISOString()};
  }
  function validarRegistro(info,lote) {
    if (!lote) throw Error('Selecione um lote existente.');
    const tipo = texto(info.tipo), etapa=Number(info.etapa);
    if (!TIPOS.includes(tipo)) throw Error('Classificação de evento inválida.');
    if (!Number.isInteger(etapa) || etapa<0 || etapa>=ETAPAS.length) throw Error('Etapa inválida.');
    if (etapa > lote.etapa + 1) throw Error('Não é permitido saltar etapas.');
    if (etapa === 5 || etapa === 8) {
      if (tipo === 'ACAO_EFETIVA_INFORMADA') throw Error('Publicação ou encerramento não podem ser declarados efetivos sem integração e leitura independente.');
    }
    const descricao = texto(info.descricao,700), responsavel=texto(info.responsavel,100);
    if (descricao.length<12 || !responsavel) throw Error('Descreva o fato (mínimo 12 caracteres) e informe o responsável.');
    const sha = texto(info.sha,64).toLowerCase();
    if (sha && !SHA_RE.test(sha)) throw Error('SHA-256 deve conter exatamente 64 caracteres hexadecimais.');
    const referencia = texto(info.referencia,240);
    if (referencia && /(?:\s|javascript:|data:|<|>)/i.test(referencia)) throw Error('Referência contém caracteres não permitidos.');
    const checkpoint = texto(info.checkpoint,180);
    if (etapa > lote.etapa && !checkpoint) throw Error('Para avançar no registro de etapa, informe um checkpoint externo.');
    return {id:uuid(),etapa,tipo,descricao,responsavel,sha,referencia,checkpoint,instante:new Date().toISOString(),prova:'DECLARACAO_LOCAL_NAO_VERIFICADA'};
  }
  function estatisticas(lotes, total=110000) {
    const ativos=lotes.filter(l=>l.estado!=='ARQUIVADO');
    const cadastrados=ativos.reduce((n,l)=>n+(l.fim-l.inicio+1),0);
    return {estimado:total,cadastrados,sucessoInformado:ativos.reduce((n,l)=>n+l.informadosSucesso,0),falhaInformada:ativos.reduce((n,l)=>n+l.informadosFalha,0),validadoExternamente:0,lotesAtivos:ativos.length,pendentes:Math.max(total-cadastrados,0)};
  }
  function conciliar(lote, campos) {
    if (!lote) throw Error('Selecione um lote para conciliar.');
    const nomes=['origem','baixados','conferidos','internos','publicados'];
    const valores=Object.fromEntries(nomes.map(n=>[n,Number(campos[n])]));
    const total=lote.fim-lote.inicio+1;
    if (!nomes.every(n=>Number.isSafeInteger(valores[n])&&valores[n]>=0&&valores[n]<=total)) throw Error('Contagens de reconciliação inválidas ou superiores ao total do lote.');
    const sha=texto(campos.shaManifesto,64).toLowerCase();
    if (Object.values(valores).some(x=>x>0) && !SHA_RE.test(sha)) throw Error('Informe SHA-256 válido do manifesto informado para registrar contagens positivas.');
    const diffs=[];for(let i=1;i<nomes.length;i++)if(valores[nomes[i]]!==valores[nomes[i-1]])diffs.push(`${nomes[i-1]}=${valores[nomes[i-1]]} x ${nomes[i]}=${valores[nomes[i]]}`);
    return {...valores,shaManifesto:sha,responsavel:texto(campos.responsavel,100)||lote.responsavel,divergencias:diffs,status:diffs.length?'DIVERGENCIA_INFORMADA':valores.origem>0?'CONTAGENS_IGUAIS_INFORMADAS':'SEM_PROCESSAMENTO_INFORMADO',prova:'DECLARACAO_LOCAL_NAO_VERIFICADA',instante:new Date().toISOString()};
  }
  function validarConfig(c) {
    const limite=Number(c.limite), paralelismo=Number(c.paralelismo), retry=Number(c.retry), backoff=Number(c.backoff), teto=Number(c.teto);
    if (![limite,paralelismo,retry,backoff,teto].every(Number.isSafeInteger) || limite<1 || limite>1000 || paralelismo<1 || paralelismo>4 || retry<0 || retry>8 || backoff<1 || backoff>300 || teto<backoff || teto>3600) throw Error('Configuração fora dos limites seguros definidos.');
    return {limite,paralelismo,retry,backoff,teto,modo:'DRY_RUN',publicacao:'BLOQUEADA',dlq:true};
  }
  function validarImportacao(s) {
    if (!s || s.schema!==1 || !Array.isArray(s.lotes) || !Array.isArray(s.eventos) || !s.config || !Array.isArray(s.links) || !s.scripts) throw Error('Arquivo de backup incompatível.');
    if (s.lotes.length>MAX_ENTRADAS || s.eventos.length>10000 || s.links.length>1000) throw Error('Backup excede limites seguros.');
    validarConfig(s.config);
    const todos=[];
    for (const l of s.lotes) {
      const p=normalizarLote({inicio:l.inicio,fim:l.fim,origem:l.origem,destino:l.destino,responsavel:l.responsavel,limite:1000},todos);
      if (!l.id || !l.chave || l.chave!==p.chave || typeof l.estado!=='string' || !Array.isArray(l.evidencias)) throw Error('Lote inválido no arquivo de backup.');
      todos.push(l);
    }
    return true;
  }
  return {ETAPAS,TIPOS,TIPO_LABEL,SHA_RE,chave,normalizarLote,atualizarQuantidades,validarRegistro,estatisticas,validarConfig,validarImportacao,conciliar,texto,uuid};
})();
if (typeof module !== 'undefined' && module.exports) module.exports = LotesCore;
