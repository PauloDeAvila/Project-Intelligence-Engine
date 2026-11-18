# Snapshot independente da cena Blender

Foi executada uma leitura canônica somente-leitura via PIE no Blender 5.3.0.
O payload ordena objetos por nome e inclui tipo, localização e materiais.

- Cena: `Scene`.
- Objetos mesh: 64.
- Payload canônico: 6.813 caracteres.
- SHA-256: `7de1f6826295728782204299b599ebbbca0ed2df697caca7ec4d0eaa98e6df1c`.
- Cena modificada: não.

Essa evidência fortalece a proveniência do benchmark Blender. O hash do gate
anterior continua sendo o hash do oráculo da tarefa; este é o hash independente
do estado observado na cena ao vivo.

Evidência: `blender-live-scene-snapshot-20261116.json`.
