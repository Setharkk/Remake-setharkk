# Première pièce partagée : montée à l’échelle

Cette version élargit la première pièce sans lui ajouter d’essaim, de dialogue ou d’exécuteur réel. Elle reste un laboratoire synthétique. Le [protocole](SCALING_PROTOCOL.md) fixe les budgets, les horizons et les conditions ; le [rapport](FIRST_PIECE_SCALE_RESULTS.md) publie les résultats et les limites.

Les [corrections de la revue](CURRENT_FIXES.md) sont livrées : collecte atteignable, validation bornée sans progrès, scores servis cohérents et état partagé au format 2 avec migration explicite. Les résultats restent limités aux distributions et budgets annoncés ; ce rapport porte sur le moteur fini. Le [mode renouvelable](RENEWABLE_SEARCH.md) retire maintenant son plafond à vie avec risque sommable et mémoire bornée. Les [résultats longs](RENEWABLE_SEARCH_RESULTS.md) exposent les échecs de rétention et de validation qui persistent.

## Ce qui change

La version temporelle conserve un modèle par contexte et sélectionne une seule relation parmi dix symboles fixes. La version partagée conserve **une seule banque neuronale pour tous les contextes**, reçoit des symboles opaques liés dynamiquement et sélectionne des combinaisons d’au plus trois relations.

| Élément | Version temporelle | Version partagée |
|---|---|---|
| Symboles | Dix entiers fixes | Chaînes opaques, budget configurable jusqu’à 128 |
| Actions | Deux | De deux à seize |
| Contextes | Jusqu’à huit ; deux dans l’expérience publiée | Jusqu’à trente-deux ; deux, huit et seize dans l’essai de montée à l’échelle |
| Routage appris | Une présence ou un premier ordre d’apparition par contexte | Une combinaison globale de jusqu’à trois présences, ordres ou égalités de contexte |
| Poids | Banques distinctes par contexte | Une banque commune, plus un contrôle de même capacité |
| Ressources | Budgets par contexte | Mémoire bornée par contexte, recherche et paramètres communs bornés |
| Validation | Gains contre contrôle et modèle servi | Mêmes gains, périmètre fixé avant validation et garde de conservation sur les autres contextes |

Les contextes observables sont des entrées possibles ; les règles cachées ne sont jamais fournies. Passer de huit à seize contextes n’alloue pas de nouveaux neurones. Cela ne signifie pas que trois prédicats peuvent exprimer trente-deux règles indépendantes arbitraires.

## Mathématiques du réseau

Chaque paramètre neuronal est un point q sur la sphère unité S², de courbure +1. Sa distance à une ancre c est d(q,c)=acos(q·c). Avec deux ancres fixes c₀ et c₁, la probabilité d’un succès est :

p(y=1 | q) = sigmoid((d(q,c₀)² − d(q,c₁)²) / τ), avec τ=0,5.

L’apprentissage de l’issue binaire y minimise l’entropie croisée. Le gradient riemannien est :

g = 2(p−y)(Log_q(c₁)−Log_q(c₀)) / τ.

La mise à jour est q′=Exp_q(−ηg), avec projection du résidu numérique normal, pas de gradient matriciel euclidien appris. Le pas vaut 0,03/sqrt(1+n/100), où n compte les mises à jour de ce neurone ; le déplacement tangent est borné à 0,2. La normalisation dans l’application exponentielle corrige seulement l’arrondi de calcul.

Chaque combinaison de k prédicats binaires donne un indice de route r=Σ 2^j f_j(observations,contexte). La banque alloue 2^max_features routes par action. Pour quatre actions et trois prédicats au maximum :

- Modèle servi : 32 points S², 96 coordonnées stockées, 64 degrés de liberté intrinsèques.
- Contrôle : même capacité, même nombre de mises à jour, routage aléatoire.
- Total en service : 64 points, 192 coordonnées, 128 degrés de liberté intrinsèques.
- Deux banques proposées supplémentaires pendant une validation : maximum de 128 points, 384 coordonnées et 256 degrés de liberté intrinsèques.

Chaque point possède deux degrés de liberté géométriques ; sa lecture fournit une seule probabilité binaire. Les registres de symboles, les compteurs, la mémoire et le routage sont des états discrets, comptés séparément. Ce réseau demeure une banque compacte de neurones à prototypes ; ce n’est pas encore un réseau profond ni un modèle génératif général du monde. Sa géométrie courbe est effective, mais aucun avantage de la courbure sur une capacité euclidienne identique n’a été établi par cet essai.

## Recherche de relations et changement de règle

La mémoire conserve les présences et l’ordre des premières occurrences. Répéter un symbole ne modifie pas cet ordre. La recherche utilise les anciens retours pour comparer des combinaisons par score logarithmique lissé. Les intersections de bitsets et leurs comptages évitent de rescanner chaque épisode pour chaque combinaison.

Elle examine au plus 96 prédicats par défaut, tous leurs couples, puis les extensions des douze meilleurs couples et des couples du programme déjà admis. Conserver ces dernières possibilités permet d’étendre une relation utile même si un changement fait disparaître son gain marginal. Ce mécanisme ne découvre pas automatiquement n’importe quelle relation nouvelle.

Les banques proposées sont ajustées sur les anciens épisodes puis figées. La décision emploie seulement de nouveaux retours. Les banques servies continuent de recevoir un gradient pendant cette validation. Les gains contre le contrôle et contre la prédiction effectivement servie doivent dépasser leur incertitude et le coût du programme.

`min_records` est une cible d’ajustement adaptée aux buffers effectivement alimentés. Une mémoire pleine peut autoriser un ajustement avec les données disponibles après le warmup ; les seuils de support ne changent pas. Les métriques annoncent le besoin de collecte.

Après une première admission, un contexte présentant une erreur élevée déclenche une validation sur ce périmètre. Une garde de score mesure aussi les autres contextes. Sa borne est uniforme dans le temps pour permettre des rythmes de retour différents. Avec un seul contexte réellement alimenté, la validation est globale. Une validation ciblée expire après `trial_stall_limit=4096` retours appris consécutifs sans progrès de son contexte ; elle libère ses candidats sans admission ni remboursement d’essai. Sa frontière d’attente est conservée à la reprise. Le [protocole](SCALING_PROTOCOL.md) détaille les hypothèses et les formules : l’admission ne garantit pas une performance future ou une absence d’oubli transitoire.

## Interfaces et reprise

`SharedAdapter` conserve les [contrats JSON version 1](SYSTEM_ARCHITECTURE.md). Les observations sont `stream.symbol` avec un `payload.value` opaque, puis `stream.end` avec la valeur `sealed`. Les capacités annoncent la taille maximale du vocabulaire, les actions, les contextes et le budget de prédicats.

Les noms d’action restent opaques, leurs arguments sont actuellement vides, et la mesure reste `lab.success/binary`. Une proposition sélectionne un candidat effectivement évalué. Une requête en vol est liée à son exécuteur ; un reçu identique ne réentraîne pas le modèle.

L’implémentation possède l’identité `first_piece.shared-compositions-s2.v1`. Elle refuse la conversion implicite des anciens snapshots. Le checkpoint du cœur est au format 2. Une restauration d’un ancien format 1 demande `SharedLearner.migrate_checkpoint_v1` ou `SharedAdapter.migrate_checkpoint_v1` avant `restore` ; les validations inachevées sont clôturées sans admission ni remise à zéro des essais. Le checkpoint contient le vocabulaire, les correspondances de contextes, les bitsets hexadécimaux, la mémoire bornée, les quatre banques éventuelles, les résumés de validation, les budgets, le RNG, l’ordre du flux et une requête éventuellement en attente.

La copie transactionnelle spécialisée détache les objets que les opérations peuvent modifier. Elle partage en lecture les anciens enregistrements, qui ne sont jamais réécrits. Les snapshots et métriques exposés restent des copies entièrement détachées. L’interface reste synchrone, avec un flux et une action en vol : ce n’est pas encore une ingestion parallèle d’essaim.

## Exécution Windows ou Linux

Python 3.11 et la bibliothèque standard suffisent. Aucune dépendance CUDA ; la RTX n’est pas utilisée pour ce laboratoire.

```powershell
git clone https://github.com/Setharkk/Remake-setharkk.git
cd Remake-setharkk
python -m unittest discover -s first_piece/tests -v
python -m first_piece.scale_run --out results/scale --seeds 0 1 2
python -m first_piece.scale_run --out results/scale --final-only --eval-n 1024
```

Le premier programme écrit les rapports et les états complets avant et après changement. Le second restaure ces états pour une nouvelle évaluation sans entraînement. La reprise d’une session en cours est disponible par l’API `SharedAdapter.restore` / `SharedLearner.restore` ; le CLI d’expérience ne reprend pas automatiquement un entraînement interrompu.

## Limites restantes

Les retours sont binaires, les actions sont explorées uniformément et les épisodes sont scellés par le monde. Le vocabulaire n’a pas de sens textuel appris ; les symboles sont discrets. Les trois prédicats ne suffisent pas à toutes les règles. Une relation pertinente peut sortir du pool et une combinaison pure de trois variables peut rester invisible avant toute admission.

La mémoire est bornée, donc les vieilles situations peuvent disparaître. Après seize essais par défaut, les gradients continuent mais la recherche de nouvelle structure s’arrête. Ni croissance illimitée, ni allocation automatique de nouveaux neurones, ni gestion durable des objectifs n’est implémentée.

Les évaluations de transfert portent sur un contexte neuf avec des symboles et une règle connus. Elles ne prouvent pas un transfert à des applications inconnues ou à un nouveau type de tâche. Aucun des scores ne démontre un paradigme inédit ou un cortex autonome.
