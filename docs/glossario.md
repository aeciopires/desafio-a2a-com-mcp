<!-- TOC -->
- [Glossário](#glossário)
<!-- TOC -->

# Glossário

| Termo | O que é | Analogia |
|---|---|---|
| **MCP** (Model Context Protocol) | protocolo para um host expor e consumir ferramentas, recursos e prompts de um servidor | a tomada padrão: qualquer aparelho que segue o padrão encaixa |
| **Host MCP** | aplicação que cria clientes MCP e usa as capacidades dos servidores; aqui, o agente | a pessoa que liga os aparelhos na tomada |
| **Tool** | ação que o servidor executa (`reservar_sala`) | um botão do painel |
| **Resource** | conteúdo que a aplicação lê quando quiser (`politica://uso`) | um manual pendurado na parede |
| **Streamable HTTP** | transporte MCP sobre HTTP; aqui sem sessão (stateless), um POST por request | um balcão que atende por senha, sem lembrar de ninguém |
| **`_meta`** | metadados que viajam em cada request (versão, capabilities, `traceparent`) | os documentos que você leva a cada ida ao cartório |
| **Capability** | o que o cliente declara saber fazer (ex.: `elicitation.form`) | "falo inglês" no currículo |
| **Elicitation (form mode)** | pedido de informação estruturada ao usuário, com um schema | um formulário de múltipla escolha |
| **MRTR** (multi-round-trip request) | o servidor termina a resposta com `input_required`, e o cliente volta com um **request novo** levando a resposta | o garçom que volta à mesa e faz um pedido novo à cozinha |
| **`input_required`** | `resultType` que diz "preciso de mais informação" | "faltou um documento" |
| **`requestState`** | estado opaco e lacrado que o cliente ecoa no retry | envelope com lacre de cera |
| **`inputRequests` / `inputResponses`** | perguntas do servidor / respostas do cliente, casadas pela mesma chave | perguntas numeradas e respostas com o mesmo número |
| **A2A** (Agent2Agent) | protocolo para agentes se descobrirem e delegarem tarefas entre si | a central telefônica entre empresas |
| **Agent Card** | identidade pública do agente em `/.well-known/agent-card.json` | o cartão de visita |
| **Skill** | capacidade anunciada no card (`reservar-sala`) | o serviço listado no cartão |
| **Task** | unidade de trabalho com id, estado e produto | a senha de atendimento |
| **`TASK_STATE_INPUT_REQUIRED`** | Task interrompida esperando o cliente | atendimento pausado, senha ainda válida |
| **Artifact** | produto da Task (`reserva`) | o recibo entregue no final |
| **Opacidade** | quem chama o agente não sabe se há um LLM, um grafo ou um `if` por trás | o atendente de telemarketing: você não vê o roteiro |
| **`traceparent`** | header W3C com trace-id e span-id | o código de rastreio da encomenda |
| **Span / Trace** | uma etapa / o caminho completo de um pedido | uma parada / o trajeto inteiro no GPS |
| **Exemplar** | ponto de uma métrica que carrega o trace-id de uma requisição real | a foto do radar com a placa do carro |
| **Structured metadata (Loki)** | campos anexados a uma linha de log sem virar label | etiqueta presa na caixa, fora do endereço |
