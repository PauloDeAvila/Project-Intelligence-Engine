# Probe dos domínios reais — repetição com fixture local

O checkout atual agora contém uma fixture Web determinística, com SHA-256
`af853a1c488e2a0d6d651446178066decabb9d801305982f2e226ca69d98de99`.

Com um servidor HTTP local temporário, o gateway PIE conseguiu navegar,
capturar o snapshot e clicar no botão da fixture. O marcador
`PIE_WEB_FIXTURE_V1` apareceu no snapshot após o clique. Porém, a ferramenta
`pie_web_context` falhou ao processar o snapshot com:

`PIE_WEB_CONTEXT_FAILED: Internal response is not a valid browser snapshot`.

O Blender continuou bloqueado pelo handshake `WinError 10053`. Nenhuma página
externa ou cena Blender foi modificada e nenhum benchmark de modelo foi
iniciado.
