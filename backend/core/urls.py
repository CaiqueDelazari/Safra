from django.urls import path

from core.views import BuscaGlobalView, DashboardView, MidiaView, SaudeView, TarefaView

urlpatterns = [
    path("saude/", SaudeView.as_view(), name="saude"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("busca/", BuscaGlobalView.as_view(), name="busca-global"),
    # Acompanhamento de qualquer trabalho em fila: lote, importação, envio.
    path("tarefas/<str:task_id>/", TarefaView.as_view(), name="tarefa"),
    # Arquivo só sai por aqui, com token assinado — ver core/midia.py.
    path("midia/<str:token>/", MidiaView.as_view(), name="midia"),
]
