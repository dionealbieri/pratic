Correção EPI e Dados da Empresa

Ajustes aplicados:
- Botão Comprovante agora pode gerar pelo funcionário selecionado, por uma única linha visível ou pelo botão de comprovante da própria linha.
- Adicionado botão de comprovante em cada registro de entrega de EPI.
- Corrigido salvamento dos Dados da Empresa: campos novos agora são criados no banco se ainda não existirem.
- Incluídos campos padrão de endereço da empresa no banco.
- Comprovante usa dados da empresa com compatibilidade para o campo antigo empresa_endereco.

Arquivos alterados:
- backend/database.py
- backend/rotas/configuracoes.py
- backend/rotas/epi.py
- frontend/js/app.js
