# Consulta seletiva Blender ao vivo

O gateway `pie-blender-optimized` executou `pie_blender_get_object` para o
objeto `Cube` na cena atual, sem alterar a cena. A resposta preservou o nome,
tipo, localização e material: `Cube`, `MESH`, `[0.0, 0.0, 0.0]` e `Material`.

Uma segunda leitura `get_scene_info` confirmou a mesma cena padrão com 1 mesh,
1 luz e 1 câmera.

Esta é uma validação funcional do contrato seletivo ao vivo. Não contém uso de
provider nem economia certificada, e não substitui o A/B da fixture
`PIE_Large_Cube_00`.
