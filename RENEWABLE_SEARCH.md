# Première pièce : recherche renouvelable

Ce mode reste une référence restaurable. Le [mode consolidé](CONSOLIDATION.md) ajoute une mémoire protégée et une validation prolongée ; ses [résultats et coûts](CONSOLIDATION_RESULTS.md) sont publiés séparément.

Le mode continu utilise `RenewableLearner` ou `RenewableAdapter`.
Le moteur historique `SharedLearner` reste disponible comme référence à budget
fini. Les deux partagent la même banque neuronale S², le même routage et les
mêmes interfaces d'observation et de résultat.

## Utilisation et sauvegarde

Python 3.11, bibliothèque standard ; Windows ou Linux, CPU. Cette expérience
ne dépend pas de CUDA et ne mesure pas la RTX.

```python
import json
from pathlib import Path
from first_piece.renewable_adapter import RenewableAdapter

cortex = RenewableAdapter(actions=("action.a", "action.b", "action.c", "action.d"))
# Envoyer les observations, choisir une proposition puis livrer son reçu
# avec les mêmes contrats que SharedAdapter.
Path("cortex.json").write_text(
    json.dumps(cortex.checkpoint(), ensure_ascii=False), encoding="utf-8")
cortex = RenewableAdapter.restore(
    json.loads(Path("cortex.json").read_text(encoding="utf-8")))
```

Les compteurs à vie, le RNG, les poids, la validation en cours, le budget de
risque et la requête en attente sont restaurés. Le cœur écrit le format 3,
identité `first_piece.renewable-compositions-s2.v1`. Le conteneur d'adaptateur
et les messages conservent leur format/version 1.

Pour importer explicitement un état partagé au format 2 :

```python
from first_piece.renewable_adapter import RenewableAdapter
converted = RenewableAdapter.from_finite_checkpoint(old_shared_adapter_state)
cortex = RenewableAdapter.restore(converted)
```

Pour le cœur seul, utiliser `RenewableLearner.from_finite_checkpoint`.
Un ancien état partagé au format 1 doit d'abord suivre la migration publiée
dans [CURRENT_FIXES.md](CURRENT_FIXES.md), puis cet import. L'import conserve
les admissions et une validation format 2 en cours, sans reconstruire des
données manquantes. Le budget historique ne disparaît pas : les métriques
annoncent une borne totale 0,10 pour un import et 0,05 pour un modèle neuf.

La sauvegarde montrée illustre la sérialisation. L'appelant doit assurer une
écriture durable et cohérente avec son journal pour résister à une panne ;
l'adaptateur ne fournit pas ce journal d'exécution physique.

## Budget mesurable

`max_attempts` désigne la taille du bloc dans ce mode, 16 par défaut.
Le compteur `attempts` conserve toutes les tentatives de la session.
Le modèle renouvelle automatiquement la recherche après clôture du dernier
essai et expiration du cooldown, si les données et l'erreur justifient
une nouvelle recherche. Il n'ajoute ni poids, ni contexte caché, ni remise
à zéro des compteurs d'apprentissage.

Les métriques exposent `search_mode`, `search_block`, `block_alpha`,
`allocated_alpha_upper_bound`, `lifetime_alpha_upper_bound`,
le résumé `renewal` et les limites du journal. Les capacités de l'adaptateur
annoncent le mode, la taille du bloc et la borne de risque à vie.
Les nombres alpha représentent des budgets statistiques théoriques :
ils ne sont ni une confiance dans chaque réponse ni un taux d'erreur mesuré.

Un modèle neuf alloue au bloc e :
`alpha_e = 0,05 / [e(e+1)]`. Sa somme est 0,05.
L'import conserve le premier bloc historique 0,05 et alloue ensuite
`alpha_e = 0,05 / [e(e-1)]`, soit 0,05 supplémentaire.
Les [formules et expériences déclarées](RENEWABLE_SEARCH_PROTOCOL.md)
détaillent les comparaisons, horizons et conditions.

La mémoire détaillée garde au plus un bloc : 16 recherches et 48 décisions
avec les réglages par défaut. Le résumé compte le préfixe archivé, ses
ajustements et admissions, et la dernière admission utile aux poids actifs.
La reprise vérifie les identités de tentatives, bornes d'incertitude,
mises à jour totales et compteurs des banques contre ce résumé.
Elle ne reconstitue pas le détail des anciennes expériences archivées.
Un journal complet doit être conservé par l'appelant si nécessaire.

## Reproduire

```powershell
git clone https://github.com/Setharkk/Remake-setharkk.git
cd Remake-setharkk
python -m unittest discover -s first_piece/tests -v
python -m validation.renewable_probe --out results/renewable.json
```

La sonde exporte les courbes, les résultats par contexte, les journaux
expérimentaux, les limites observées et la comparaison avec le moteur fini.
Elle valide aussi une reprise dans un bloc ultérieur, sur les mêmes retours
futurs. Les durées sont celles des runners CPU, pas de ton PC.

Les [résultats complets](RENEWABLE_SEARCH_RESULTS.md) publient les réussites et les échecs :
la reprise après bruit initial fonctionne ; la conservation sous bruit et
l'admission des changements minoritaires restent insuffisantes.

## Portée

Les paramètres appris restent des points sphériques, sans agrandir le réseau.
Le renouvellement enlève le plafond de 16 tentatives à vie. Il n'enlève pas
les limites de 128 symboles, 32 contextes, 16 actions ou trois prédicats.

Les gains doivent être décidés en au plus 4 096 nouveaux retours principaux ;
le budget décroissant peut rendre de faibles améliorations indécidables.
Un essai expiré ne crée aucun nouveau regard statistique et ne rembourse pas
le risque. L'expiration et le cooldown comptent des retours appris, pas des
secondes, ni des actions annulées.

Les gradients des poids actifs continuent pendant le bruit et les validations :
la garde d'admission protège un remplacement, pas tous les gradients continus.
La conservation de compétences n'est donc pas garantie.
Le pas diminue toujours avec l'âge des neurones. Les buts, le dialogue,
l'essaim autonome, les actions PC et l'avantage de la courbure restent
des travaux distincts.
