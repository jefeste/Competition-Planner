import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import time

# ============================================
# COUCHE 1 : UTILITAIRES DE BASE (Pure Functions)
# ============================================

def parse_start_time(time_str):
    """Parse une chaîne horaire en datetime"""
    return datetime.strptime(time_str, "%H:%M")


def build_single_rider_times(start_datetime, params):
    """
    Calcule les horaires d'un cavalier à partir de son heure de départ
    
    Input:
        - start_datetime: datetime du départ dressage
        - params: dict avec d_dressage, d_cross, d_saut, d_pause1, d_pause2
    
    Output: dict avec 'dressage', 'cross', 'saut' (tuples de start/end)
    """
    d_dressage = timedelta(minutes=params['d_dressage'])
    d_cross = timedelta(minutes=params['d_cross'])
    d_saut = timedelta(minutes=params['d_saut'])

    c_dress_start = start_datetime
    c_dress_end = c_dress_start + d_dressage
    c_cross_start = c_dress_end + timedelta(minutes=params['d_pause1'])
    c_cross_end = c_cross_start + d_cross
    c_saut_start = c_cross_end + timedelta(minutes=params['d_pause2'])
    c_saut_end = c_saut_start + d_saut

    return {
        'dressage': (c_dress_start, c_dress_end),
        'cross': (c_cross_start, c_cross_end),
        'saut': (c_saut_start, c_saut_end)
    }


def calculate_max_reset(params):
    """Retourne le temps de reset maximum parmi les 3 terrains"""
    return max(params['reset_dressage'], params['reset_cross'], params['reset_saut'])


def calculate_max_duration(params):
    """Retourne la durée d'épreuve maximale"""
    return max(params['d_dressage'], params['d_cross'], params['d_saut'])


# ============================================
# COUCHE 2 : VÉRIFICATION DE CONFLITS
# ============================================

def check_reset_conflicts(candidate_times, last_rider, params):
    """
    Vérifie que le cavalier candidat respecte les temps de reset
    avec le dernier cavalier du schedule
    
    Output: bool (True si pas de conflit)
    """
    c_dress_start = candidate_times['dressage'][0]
    c_cross_start = candidate_times['cross'][0]
    c_saut_start = candidate_times['saut'][0]
    
    prev_dress_end = last_rider['dressage'][1]
    prev_cross_end = last_rider['cross'][1]
    prev_saut_end = last_rider['saut'][1]
    
    if c_dress_start < prev_dress_end + timedelta(minutes=params['reset_dressage']):
        return False
    if c_cross_start < prev_cross_end + timedelta(minutes=params['reset_cross']):
        return False
    if c_saut_start < prev_saut_end + timedelta(minutes=params['reset_saut']):
        return False
    
    return True


def check_shared_arena_conflict(candidate_times, schedule, params):
    """
    Vérifie les conflits sur terrain partagé dressage/saut
    
    Output: bool (True si pas de conflit)
    """
    buffer = timedelta(minutes=params['transition_shared'])
    c_dress_start, c_dress_end = candidate_times['dressage']
    c_saut_start, c_saut_end = candidate_times['saut']
    
    for other in schedule:
        other_saut_start, other_saut_end = other['saut']
        other_dress_start, other_dress_end = other['dressage']
        
        # Dressage candidat vs Saut autre
        if (c_dress_start < other_saut_end + buffer) and (c_dress_end > other_saut_start - buffer):
            return False
        # Saut candidat vs Dressage autre
        if (c_saut_start < other_dress_end + buffer) and (c_saut_end > other_dress_start - buffer):
            return False
    
    return True


def verify_no_conflicts(candidate_start, schedule, params):
    """
    Vérification complète : reset + shared arena si nécessaire
    
    Output: bool (True si tout OK)
    """
    candidate_times = build_single_rider_times(candidate_start, params)
    
    # Vérifier les resets avec le dernier cavalier
    if schedule:
        if not check_reset_conflicts(candidate_times, schedule[-1], params):
            return False
    
    # Vérifier le terrain partagé si activé
    if params['shared_arena']:
        if not check_shared_arena_conflict(candidate_times, schedule, params):
            return False
    
    return True


# ============================================
# COUCHE 3 : CALCUL INCRÉMENTAL
# ============================================

def calculate_next_rider_incremental(schedule, params, start_from=None):
    """
    Calcule le prochain cavalier en mode incrémental (recherche pas à pas)
    
    Output: dict avec 'id', 'dressage', 'cross', 'saut'
    """
    if start_from is None:
        if schedule:
            start_from = schedule[-1]['dressage'][0] + timedelta(minutes=1)
        else:
            start_from = parse_start_time(params['start_time'])
    
    step = timedelta(seconds=30)
    start_candidate = start_from
    
    # Recherche du premier slot valide
    max_iterations = 2000  # Sécurité
    for _ in range(max_iterations):
        if verify_no_conflicts(start_candidate, schedule, params):
            times = build_single_rider_times(start_candidate, params)
            return {
                'id': len(schedule) + 1,
                'dressage': times['dressage'],
                'cross': times['cross'],
                'saut': times['saut']
            }
        start_candidate += step
    
    raise RuntimeError("Impossible de trouver un slot valide après 2000 itérations")


# ============================================
# COUCHE 4 : DÉTECTION DE PATTERN (shared_arena == True)
# ============================================

def find_block_size_and_pattern(params, start_time):
    """
    Trouve la taille du bloc σ et le pattern pour shared_arena == True
    
    Output: dict avec 'sigma', 'lambda', 'block_schedule'
    """
    schedule_bloc = []
    
    # Calculer cavaliers incrémentalement jusqu'à trouver le bloc
    for k in range(1, 100):  # Limite sécurité (théoriquement toujours < 50)
        rider = calculate_next_rider_incremental(schedule_bloc, params, start_time if k == 1 else None)
        schedule_bloc.append(rider)
        
        # TEST : Cavalier k commence-t-il après que cavalier 1 ait fini ?
        cavalier_1_end = schedule_bloc[0]['saut'][1]
        cavalier_1_fully_free = cavalier_1_end + timedelta(minutes=params['reset_saut'])
        cavalier_k_start = schedule_bloc[-1]['dressage'][0]
        
        if cavalier_k_start >= cavalier_1_fully_free:
            # On a trouvé σ = k !
            # Lambda = intervalle entre le début du cavalier 1 et le début du cavalier k
            # Le cavalier k+1 (premier du prochain bloc) peut commencer au même moment que k
            sigma = k-1
            lambda_minutes = (schedule_bloc[-1]['dressage'][0] - schedule_bloc[0]['dressage'][0]).total_seconds() / 60
            
            return {
                'sigma': sigma,
                'lambda': lambda_minutes,
                'block_schedule': schedule_bloc
            }
    
    raise RuntimeError("Pattern non trouvé après 100 cavaliers (impossible théoriquement)")


def duplicate_pattern(block_schedule, lambda_minutes, total_riders, params):
    """
    Duplique le pattern pour générer tous les cavaliers
    
    Output: Liste complète de tous les cavaliers
    """
    sigma = len(block_schedule)-1
    schedule = []
    
    # Calculer le nombre de blocs complets et cavaliers restants
    num_full_blocks = total_riders // sigma
    remaining_riders = total_riders % sigma
    
    # Dupliquer les blocs complets
    for block_num in range(num_full_blocks):
        for idx_in_block in range(sigma):
            original_rider = block_schedule[idx_in_block]
            offset = timedelta(minutes=lambda_minutes * block_num)
            
            new_start = original_rider['dressage'][0] + offset
            times = build_single_rider_times(new_start, params)
            
            schedule.append({
                'id': block_num * sigma + idx_in_block + 1,
                'dressage': times['dressage'],
                'cross': times['cross'],
                'saut': times['saut']
            })
    
    # Cavaliers restants (bloc partiel)
    for idx in range(remaining_riders):
        original_rider = block_schedule[idx]
        offset = timedelta(minutes=lambda_minutes * num_full_blocks)
        
        new_start = original_rider['dressage'][0] + offset
        times = build_single_rider_times(new_start, params)
        
        schedule.append({
            'id': num_full_blocks * sigma + idx + 1,
            'dressage': times['dressage'],
            'cross': times['cross'],
            'saut': times['saut']
        })
    
    return schedule


# ============================================
# COUCHE 5 : GÉNÉRATEURS DE PLANNING
# ============================================

def generate_schedule_simple_pattern(params):
    """
    Génération pour shared_arena == False
    Pattern simple en escalier avec décalage constant
    
    Complexité: O(N)
    """
    start_time = parse_start_time(params['start_time'])
    nb_cavaliers = params['nb_cavaliers']
    
    # Calcul du décalage constant
    delta = calculate_max_reset(params) + calculate_max_duration(params)
    
    schedule = []
    for i in range(nb_cavaliers):
        start_i = start_time + timedelta(minutes=i * delta)
        times = build_single_rider_times(start_i, params)
        
        schedule.append({
            'id': i + 1,
            'dressage': times['dressage'],
            'cross': times['cross'],
            'saut': times['saut']
        })
    
    return schedule


def generate_schedule_with_block_pattern(params):
    """
    Génération pour shared_arena == True
    Détection du bloc + duplication
    
    Complexité: O(σ + N) où σ << N
    """
    start_time = parse_start_time(params['start_time'])
    nb_cavaliers = params['nb_cavaliers']
    
    # PHASE 1 : Trouver le pattern
    pattern = find_block_size_and_pattern(params, start_time)
    
    # PHASE 2 : Dupliquer pour tous les cavaliers
    schedule = duplicate_pattern(
        pattern['block_schedule'],
        pattern['lambda'],
        nb_cavaliers,
        params
    )
    
    return schedule


def generate_schedule_manual(params):
    """
    Génération en mode manuel (logique préservée)
    """
    start_time = parse_start_time(params['start_time'])
    nb_cavaliers = params['nb_cavaliers']
    
    try:
        raw_intervals = params['manual_list'].replace(' ', '').split(',')
        intervals = [float(x) for x in raw_intervals if x]
    except ValueError:
        st.error("Erreur dans la liste manuelle.")
        return []
    
    if intervals:
        while len(intervals) < nb_cavaliers:
            intervals.append(intervals[-1])
    else:
        intervals = [5] * nb_cavaliers
    
    schedule = []
    current_start = start_time
    
    for i in range(nb_cavaliers):
        times = build_single_rider_times(current_start, params)
        schedule.append({
            'id': i + 1,
            'dressage': times['dressage'],
            'cross': times['cross'],
            'saut': times['saut']
        })
        
        if i < len(intervals):
            current_start = current_start + timedelta(minutes=intervals[i])
    
    return schedule


# ============================================
# COUCHE 6 : DISPATCHER PRINCIPAL
# ============================================

def calculer_planning(params):
    """
    Point d'entrée principal - Dispatcher
    
    Output: (schedule, computation_time) ou ([], None) si erreur
    """
    start_computation = time.time()
    
    try:
        # Validation du format horaire
        parse_start_time(params['start_time'])
    except ValueError:
        st.error("Format d'heure invalide.")
        return [], None
    
    # Dispatch selon le mode
    if params['mode'] == 'Manuel':
        schedule = generate_schedule_manual(params)
        computation_time = time.time() - start_computation
        return schedule, computation_time
    
    elif params['mode'] == 'Optimisation Auto':
        progress_bar = st.progress(0)
        
        if not params['shared_arena']:
            # CAS 1 : Terrains séparés - Pattern simple
            schedule = generate_schedule_simple_pattern(params)
        else:
            # CAS 2 : Terrain partagé - Détection de bloc
            schedule = generate_schedule_with_block_pattern(params)
        
        progress_bar.progress(1.0)
        computation_time = time.time() - start_computation
        return schedule, computation_time
    
    return [], None


# ============================================
# COUCHE 6.5 : OPTIMISATION DE PARAMÈTRES
# ============================================

def is_valid_parameter_set(params):
    """
    Vérifie qu'un set de paramètres est valide
    
    Contraintes:
    - Tous les paramètres doivent être > 0
    - Les transitions doivent permettre le déplacement physique
    """
    if params['d_pause1'] <= 0 or params['d_pause2'] <= 0:
        return False
    if params['reset_dressage'] < 0 or params['reset_cross'] < 0 or params['reset_saut'] < 0:
        return False
    if params['transition_shared'] < 0:
        return False
    
    # Contraintes minimales raisonnables (optionnel)
    if params['d_pause1'] < 2 or params['d_pause2'] < 2:  # Minimum 2 min pour se déplacer
        return False
    if params['transition_shared'] < 1:  # Minimum 1 min de buffer
        return False
    
    return True


def calculate_total_duration(schedule):
    """
    Calcule le temps total d'un planning en minutes
    
    Temps total = heure_fin_dernier_cavalier - heure_début_premier_cavalier
    """
    if not schedule:
        return float('inf')
    
    start = schedule[0]['dressage'][0]
    end = schedule[-1]['saut'][1]
    
    return (end - start).total_seconds() / 60


def generate_parameter_combinations(base_params, delta=3, step=1):
    """
    Génère toutes les combinaisons de paramètres autour des valeurs de base
    
    Input:
        - base_params: dict avec les paramètres actuels
        - delta: écart maximum en minutes (±delta)
        - step: pas d'incrémentation en minutes
    
    Output: liste de dicts de paramètres
    """
    params_to_optimize = ['d_pause1', 'd_pause2', 'reset_dressage', 
                          'reset_cross', 'reset_saut', 'transition_shared']
    
    # Générer les valeurs pour chaque paramètre
    param_ranges = {}
    for param in params_to_optimize:
        base_value = base_params[param]
        values = []
        for offset in range(-delta, delta + 1, step):
            values.append(base_value + offset)
        param_ranges[param] = values
    
    # Générer toutes les combinaisons
    import itertools
    combinations = []
    
    keys = list(param_ranges.keys())
    for values in itertools.product(*[param_ranges[k] for k in keys]):
        test_params = base_params.copy()
        for i, key in enumerate(keys):
            test_params[key] = values[i]
        
        # Valider les paramètres
        if is_valid_parameter_set(test_params):
            combinations.append(test_params)
    
    return combinations


def optimize_parameters(base_params, top_n=5, progress_callback=None):
    """
    Optimise les paramètres pour minimiser le temps total
    
    Input:
        - base_params: dict avec les paramètres de base
        - top_n: nombre de meilleures configurations à retourner
        - progress_callback: fonction pour mettre à jour la progression
    
    Output: liste de tuples (params, temps_total, gain)
    """
    # Générer toutes les combinaisons
    combinations = generate_parameter_combinations(base_params, delta=3, step=1)
    total_combinations = len(combinations)
    
    results = []
    
    # Calculer le temps total de base
    base_schedule, _ = calculer_planning(base_params)
    base_duration = calculate_total_duration(base_schedule) if base_schedule else float('inf')
    
    # Tester chaque combinaison
    for idx, test_params in enumerate(combinations):
        try:
            schedule, _ = calculer_planning(test_params)
            if schedule:
                duration = calculate_total_duration(schedule)
                gain = base_duration - duration
                results.append((test_params, duration, gain))
        except Exception:
            # Ignorer les combinaisons qui génèrent des erreurs
            pass
        
        # Mise à jour de la progression
        if progress_callback and (idx + 1) % 100 == 0:
            progress_callback((idx + 1) / total_combinations)
    
    # Trier par temps total croissant
    results.sort(key=lambda x: x[1])
    
    return results[:top_n], total_combinations, base_duration


# ============================================
# COUCHE 7 : INTERFACE STREAMLIT
# ============================================

st.set_page_config(page_title="Planning CCE", layout="wide")

st.markdown(
        """
        <style>
            .made-by {
                position: fixed;
                top: 60px;
                right: 20px;
                z-index: 999999;
                background: rgba(255,255,255,0.95);
                padding: 8px 14px;
                border-radius: 8px;
                font-size: 14px;
                box-shadow: 0 2px 12px rgba(0,0,0,0.15);
                border: 1px solid #ddd;
            }
            .made-by a {
                color: #0066cc;
                text-decoration: none;
            }
            .made-by a:hover {
                text-decoration: underline;
            }
            [data-testid="stSidebar"] > div:first-child {
                display: flex;
                flex-direction: column;
                height: 100vh;
            }
            .sidebar-spacer { flex: 1 1 auto; }
        </style>
        <div class="made-by">
            Made by <a href="https://jeremydigard.com" target="_blank">Jérémy Digard</a> for
            <a href="https://equissima.ch" target="_blank">Equissima</a>
            2025- 2026
        </div>
        """,
        unsafe_allow_html=True
)

st.title("🏇 Générateur de Planning Concours Complet")
st.markdown("---")

# --- BARRE LATERALE (PARAMETRES) ---
with st.sidebar:
    st.header("1. Configuration")
    start_time = st.text_input("Heure de début", "12:15")
    nb_cavaliers = st.number_input("Nombre de cavaliers", min_value=1, value=10)
    
    st.subheader("Durées (minutes)")
    d_dressage = st.number_input("Dressage", value=4.0)
    d_pause1 = st.number_input("Pause 1 (vers Cross)", value=15.0)
    d_cross = st.number_input("Cross", value=4.0)
    d_pause2 = st.number_input("Pause 2 (vers Saut)", value=7.0)
    d_saut = st.number_input("Saut", value=2.0)
    
    st.markdown("---")
    st.header("2. Mode de Calcul")
    mode = st.radio("Méthode :", ["Manuel", "Optimisation Auto"], index=1)

    manual_list = ""
    reset_dressage, reset_cross, reset_saut = 0.0, 0.0, 0.0
    shared_arena, transition_shared = True, 0.0

    if mode == "Manuel":
        manual_list = st.text_input("Liste des écarts (ex: 6, 7, 4)", "6, 7, 4")
    else:
        st.info("Temps de remise en état (Reset) entre 2 cavaliers :")
        col1, col2, col3 = st.columns(3)
        with col1: reset_dressage = st.number_input("Reset Dress.", value=1.0)
        with col2: reset_cross = st.number_input("Reset Cross", value=2.0)
        with col3: reset_saut = st.number_input("Reset Saut", value=1.5)
        
        shared_arena = st.checkbox("Même terrain (Dressage / Saut)", value=True)
        if shared_arena:
            transition_shared = st.number_input("Temps transition D/S", value=5.0)

    st.markdown('<div class="sidebar-spacer"></div>', unsafe_allow_html=True)

    generate_btn = st.button("Générer le Planning", type="primary", use_container_width=True)
    
    # Bouton d'optimisation (seulement en mode Auto avec shared_arena)
    optimize_btn = False
    if mode == "Optimisation Auto" and shared_arena:
        optimize_btn = st.button("🔍 Suggérer Optimisations", use_container_width=True)

# --- CORPS PRINCIPAL ---

if generate_btn:
    params = {
        'start_time': start_time, 'nb_cavaliers': int(nb_cavaliers),
        'd_dressage': d_dressage, 'd_pause1': d_pause1,
        'd_cross': d_cross, 'd_pause2': d_pause2, 'd_saut': d_saut,
        'mode': mode, 'manual_list': manual_list,
        'reset_dressage': reset_dressage, 'reset_cross': reset_cross, 'reset_saut': reset_saut,
        'shared_arena': shared_arena, 'transition_shared': transition_shared
    }

    schedule, computation_time = calculer_planning(params)

    if schedule:
        # Affichage du temps de traitement
        if computation_time is not None:
            if computation_time < 1:
                st.info(f"⏱️ Temps de calcul du planning : {computation_time*1000:.1f} ms")
            else:
                st.info(f"⏱️ Temps de calcul du planning : {computation_time:.2f} s")
        
        # Affichage du graphe
        fig, ax = plt.subplots(figsize=(12, nb_cavaliers * 0.5 + 2)) # Hauteur dynamique
        colors = {'dressage': '#4472C4', 'cross': '#548235', 'saut': '#C00000'}
        bar_height = 0.5
        
        for cav in schedule:
            y = cav['id']
            # Dressage
            start, end = mdates.date2num(cav['dressage'][0]), mdates.date2num(cav['dressage'][1])
            ax.barh(y, end - start, left=start, height=bar_height, color=colors['dressage'], edgecolor='white')
            ax.text(start, y - 0.35, cav['dressage'][0].strftime("%H:%M"), fontsize=8, ha='center', fontweight='bold')
            # Cross
            start, end = mdates.date2num(cav['cross'][0]), mdates.date2num(cav['cross'][1])
            ax.barh(y, end - start, left=start, height=bar_height, color=colors['cross'], edgecolor='white')
            ax.text(start, y - 0.35, cav['cross'][0].strftime("%H:%M"), fontsize=8, ha='center', fontweight='bold')
            # Saut
            start, end = mdates.date2num(cav['saut'][0]), mdates.date2num(cav['saut'][1])
            ax.barh(y, end - start, left=start, height=bar_height, color=colors['saut'], edgecolor='white')
            ax.text(start, y - 0.35, cav['saut'][0].strftime("%H:%M"), fontsize=8, ha='center', fontweight='bold')

        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=15))
        ax.set_yticks([c['id'] for c in schedule])
        ax.set_yticklabels([f"Cavalier {c['id']}" for c in schedule], fontweight='bold')
        ax.invert_yaxis()
        ax.grid(True, axis='x', linestyle='--', alpha=0.5)
        
        # Légende manuelle pour Matplotlib dans Streamlit
        legend_elements = [
            plt.Rectangle((0,0),1,1, color=colors['dressage'], label='Dressage'),
            plt.Rectangle((0,0),1,1, color=colors['cross'], label='Cross'),
            plt.Rectangle((0,0),1,1, color=colors['saut'], label='Saut (CSO)')
        ]
        ax.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=3)
        
        st.pyplot(fig)
        st.success(f"Planning généré pour {nb_cavaliers} cavaliers !")


# --- OPTIMISATION DES PARAMÈTRES ---

if optimize_btn:
    params = {
        'start_time': start_time, 'nb_cavaliers': int(nb_cavaliers),
        'd_dressage': d_dressage, 'd_pause1': d_pause1,
        'd_cross': d_cross, 'd_pause2': d_pause2, 'd_saut': d_saut,
        'mode': mode, 'manual_list': manual_list,
        'reset_dressage': reset_dressage, 'reset_cross': reset_cross, 'reset_saut': reset_saut,
        'shared_arena': shared_arena, 'transition_shared': transition_shared
    }
    
    st.markdown("---")
    st.header("🔍 Recherche des configurations optimales")
    st.info("Analyse en cours... Cette opération peut prendre quelques minutes selon le nombre de combinaisons.")
    
    # Barre de progression
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    def update_progress(value):
        progress_bar.progress(value)
        status_text.text(f"Progression : {value*100:.0f}%")
    
    # Lancer l'optimisation
    start_opt = time.time()
    results, total_tested, base_duration = optimize_parameters(params, top_n=5, progress_callback=update_progress)
    opt_duration = time.time() - start_opt
    
    progress_bar.progress(1.0)
    status_text.empty()
    
    # Afficher les résultats
    if results:
        st.success(f"✅ Optimisation terminée en {opt_duration:.1f}s ({total_tested} configurations testées)")
        
        # Configuration actuelle
        st.subheader("📊 Configuration actuelle")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Temps total actuel", f"{base_duration:.1f} min")
        with col2:
            st.write("**Paramètres actuels:**")
            st.write(f"- Pause 1: {d_pause1} min")
            st.write(f"- Pause 2: {d_pause2} min")
            st.write(f"- Reset Dress: {reset_dressage} min")
            st.write(f"- Reset Cross: {reset_cross} min")
            st.write(f"- Reset Saut: {reset_saut} min")
            st.write(f"- Transition D/S: {transition_shared} min")
        
        st.markdown("---")
        st.subheader("🏆 Top 5 Configurations Optimales")
        
        # Afficher chaque résultat
        for idx, (opt_params, duration, gain) in enumerate(results, 1):
            with st.expander(f"#{idx} - Temps: {duration:.1f} min (gain: {gain:.1f} min)", expanded=(idx==1)):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.write("**Transitions:**")
                    st.write(f"Pause 1: {opt_params['d_pause1']:.0f} min")
                    st.write(f"Pause 2: {opt_params['d_pause2']:.0f} min")
                
                with col2:
                    st.write("**Resets:**")
                    st.write(f"Dressage: {opt_params['reset_dressage']:.0f} min")
                    st.write(f"Cross: {opt_params['reset_cross']:.0f} min")
                    st.write(f"Saut: {opt_params['reset_saut']:.0f} min")
                
                with col3:
                    st.write("**Terrain partagé:**")
                    st.write(f"Transition: {opt_params['transition_shared']:.0f} min")
                    st.metric("Gain de temps", f"{gain:.1f} min", delta=f"{(gain/base_duration)*100:.1f}%")
                
                # Bouton pour appliquer cette configuration
                if st.button(f"Appliquer cette configuration", key=f"apply_{idx}"):
                    st.warning("⚠️ Pour appliquer ces paramètres, veuillez les saisir manuellement dans la barre latérale.")
        
        # Graphique comparatif
        st.markdown("---")
        st.subheader("📈 Comparaison des temps totaux")
        
        fig_comp, ax_comp = plt.subplots(figsize=(10, 4))
        
        config_names = ["Actuel"] + [f"Config #{i+1}" for i in range(len(results))]
        times = [base_duration] + [r[1] for r in results]
        colors_bar = ['#FF6B6B'] + ['#51CF66'] * len(results)
        
        ax_comp.barh(config_names, times, color=colors_bar)
        ax_comp.set_xlabel('Temps total (minutes)')
        ax_comp.set_title('Comparaison des configurations')
        ax_comp.grid(True, axis='x', alpha=0.3)
        
        # Ajouter les valeurs sur les barres
        for i, (name, time_val) in enumerate(zip(config_names, times)):
            ax_comp.text(time_val, i, f' {time_val:.1f} min', 
                        va='center', fontweight='bold')
        
        st.pyplot(fig_comp)
    else:
        st.error("❌ Aucune configuration optimale trouvée. Les paramètres actuels sont peut-être déjà optimaux.")
