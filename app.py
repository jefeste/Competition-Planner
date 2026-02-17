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

def calculer_planning(params, silent=False):
    """
    Point d'entrée principal - Dispatcher
    
    Output: (schedule, computation_time) ou ([], None) si erreur
    
    Args:
        params: dict avec les paramètres
        silent: si True, ne crée pas d'éléments UI (pour l'optimisation en batch)
    """
    start_computation = time.time()
    
    try:
        # Validation du format horaire
        parse_start_time(params['start_time'])
    except ValueError:
        if not silent:
            st.error("Format d'heure invalide.")
        return [], None
    
    # Dispatch selon le mode
    if params['mode'] == 'Manuel':
        schedule = generate_schedule_manual(params)
        computation_time = time.time() - start_computation
        return schedule, computation_time
    
    elif params['mode'] == 'Optimisation Auto':
        if not silent:
            progress_bar = st.progress(0)
        
        if not params['shared_arena']:
            # CAS 1 : Terrains séparés - Pattern simple
            schedule = generate_schedule_simple_pattern(params)
        else:
            # CAS 2 : Terrain partagé - Détection de bloc
            schedule = generate_schedule_with_block_pattern(params)
        
        if not silent:
            progress_bar.progress(1.0)
        computation_time = time.time() - start_computation
        return schedule, computation_time
    
    return [], None


# ============================================
# COUCHE 6.5 : DIAGNOSTIC ANALYTIQUE (Max-Plus)
# ============================================

def compute_bottleneck(params):
    """
    Identifie le goulot d'étranglement par analyse spectrale Max-Plus.
    
    λ = max(p_i + r_i / c_i) pour chaque étape i.
    
    En mode shared_arena:
        λ = max(p_dressage + p_saut + 2·τ, (p_cross + r_cross) / c_cross)
    En mode séparé:
        λ = max(p_dressage + r_dressage, p_cross + r_cross, p_saut + r_saut)
    
    Output: dict avec 'lambda', 'bottleneck_name', 'all_terms'
    """
    if params['shared_arena']:
        tau = params['transition_shared']
        term_shared = params['d_dressage'] + params['d_saut'] + 2 * tau
        term_cross = params['d_cross'] + params['reset_cross']
        
        terms = [
            {'name': 'Terrain partagé (Dressage + Saut + 2×Transition)',
             'value': term_shared,
             'formula': f"{params['d_dressage']:.1f} + {params['d_saut']:.1f} + 2×{tau:.1f}",
             'levers': [
                 {'param': 'd_dressage', 'label': 'Durée Dressage', 'coeff': 1},
                 {'param': 'd_saut', 'label': 'Durée Saut', 'coeff': 1},
                 {'param': 'transition_shared', 'label': 'Transition D/S', 'coeff': 2},
             ]},
            {'name': 'Cross',
             'value': term_cross,
             'formula': f"{params['d_cross']:.1f} + {params['reset_cross']:.1f}",
             'levers': [
                 {'param': 'd_cross', 'label': 'Durée Cross', 'coeff': 1},
                 {'param': 'reset_cross', 'label': 'Reset Cross', 'coeff': 1},
             ]},
        ]
    else:
        term_dress = params['d_dressage'] + params['reset_dressage']
        term_cross = params['d_cross'] + params['reset_cross']
        term_saut = params['d_saut'] + params['reset_saut']
        
        terms = [
            {'name': 'Dressage',
             'value': term_dress,
             'formula': f"{params['d_dressage']:.1f} + {params['reset_dressage']:.1f}",
             'levers': [
                 {'param': 'd_dressage', 'label': 'Durée Dressage', 'coeff': 1},
                 {'param': 'reset_dressage', 'label': 'Reset Dressage', 'coeff': 1},
             ]},
            {'name': 'Cross',
             'value': term_cross,
             'formula': f"{params['d_cross']:.1f} + {params['reset_cross']:.1f}",
             'levers': [
                 {'param': 'd_cross', 'label': 'Durée Cross', 'coeff': 1},
                 {'param': 'reset_cross', 'label': 'Reset Cross', 'coeff': 1},
             ]},
            {'name': 'Saut',
             'value': term_saut,
             'formula': f"{params['d_saut']:.1f} + {params['reset_saut']:.1f}",
             'levers': [
                 {'param': 'd_saut', 'label': 'Durée Saut', 'coeff': 1},
                 {'param': 'reset_saut', 'label': 'Reset Saut', 'coeff': 1},
             ]},
        ]
    
    # Tri par valeur décroissante
    terms.sort(key=lambda t: t['value'], reverse=True)
    
    bottleneck = terms[0]
    second = terms[1] if len(terms) > 1 else None
    
    return {
        'lambda': bottleneck['value'],
        'bottleneck': bottleneck,
        'second': second,
        'all_terms': terms,
    }


def compute_sensitivity_table(params, bottleneck_info, max_delta=5):
    """
    Calcule le tableau de sensibilité : gain par réduction de 1, 2, ... min
    sur chaque levier du goulot d'étranglement.
    
    Détecte le breakpoint où le goulot bascule.
    
    Output: dict avec 'rows' (tableau) et 'pause_gain' (levier secondaire)
    """
    Q = params['nb_cavaliers']
    current_lambda = bottleneck_info['lambda']
    second_value = bottleneck_info['second']['value'] if bottleneck_info['second'] else 0
    bottleneck = bottleneck_info['bottleneck']
    
    rows = []  # liste de dicts pour le tableau
    
    for lever in bottleneck['levers']:
        coeff = lever['coeff']
        current_param_value = params[lever['param']]
        
        for delta in range(1, max_delta + 1):
            new_param_value = current_param_value - delta
            if new_param_value < 0:
                break
            
            # Nouveau λ si on réduit ce levier
            new_lambda = current_lambda - delta * coeff
            
            # Le nouveau λ effectif est max(new_lambda, second_value)
            effective_lambda = max(new_lambda, second_value)
            
            # Gain sur λ
            delta_lambda = current_lambda - effective_lambda
            
            # Gain total sur le planning
            gain_total = (Q - 1) * delta_lambda
            
            # Breakpoint détecté ?
            breakpoint_reached = new_lambda <= second_value
            
            rows.append({
                'lever': lever['label'],
                'param': lever['param'],
                'coeff': coeff,
                'delta': delta,
                'new_value': new_param_value,
                'new_lambda': effective_lambda,
                'delta_lambda': delta_lambda,
                'gain_total': gain_total,
                'breakpoint': breakpoint_reached,
            })
            
            # Arrêter après le breakpoint
            if breakpoint_reached:
                break
    
    # Levier secondaire : pauses (gain constant de 1 min par min réduite)
    pause_levers = []
    for pause_name, pause_label in [('d_pause1', 'Pause 1'), ('d_pause2', 'Pause 2')]:
        current_val = params[pause_name]
        for delta in range(1, max_delta + 1):
            new_val = current_val - delta
            if new_val < 1:  # minimum 1 min
                break
            pause_levers.append({
                'lever': pause_label,
                'param': pause_name,
                'delta': delta,
                'new_value': new_val,
                'gain_total': delta,  # gain constant
            })
    
    return {
        'rows': rows,
        'pause_levers': pause_levers,
    }


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
    d_dressage = st.number_input("Dressage", min_value=1, value=4)
    d_pause1 = st.number_input("Pause 1 (vers Cross)",min_value=1,  value=15)
    d_cross = st.number_input("Cross", min_value=1, value=4)
    d_pause2 = st.number_input("Pause 2 (vers Saut)", min_value=1, value=7)
    d_saut = st.number_input("Saut", min_value=1, value=2)
    
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
        with col1: reset_dressage = st.number_input("Reset Dress.", min_value=0, value=1)
        with col2: reset_cross = st.number_input("Reset Cross", min_value=0, value=2)
        with col3: reset_saut = st.number_input("Reset Saut", min_value=0, value=1)
        
        shared_arena = st.checkbox("Même terrain (Dressage / Saut)", value=True)
        if shared_arena:
            transition_shared = st.number_input("Temps transition D/S", min_value=0, value=5)

    st.markdown('<div class="sidebar-spacer"></div>', unsafe_allow_html=True)

    generate_btn = st.button("Générer le Planning", type="primary", use_container_width=True)

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
        
        # --- DIAGNOSTIC & OPTIMISATION (auto en mode Auto) ---
        if mode == "Optimisation Auto":
            st.markdown("---")
            st.header("🔍 Diagnostic & Optimisation")
            
            info = compute_bottleneck(params)
            Q = int(nb_cavaliers)
            lam = info['lambda']
            bottleneck = info['bottleneck']
            second = info['second']
            
            # Pipeline delay
            L_total = d_dressage + d_pause1 + d_cross + d_pause2 + d_saut
            T_total_estimated = L_total + (Q - 1) * lam
            
            # 1. Diagnostic en 1 ligne
            st.error(f"**Goulot d'étranglement : {bottleneck['name']}  (λ = {lam:.1f} min)")
            
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.metric("λ (cadence)", f"{lam:.1f} min/cavalier")
            with col_d2:
                st.metric("Durée totale estimée", f"{T_total_estimated:.0f} min")
            
            # 2. Détail des termes
            st.caption("Détail des étapes (le max détermine λ) :")
            for term in info['all_terms']:
                marker = "🔴" if term == bottleneck else "⚪"
                st.text(f"  {marker} {term['name']} = {term['formula']} = {term['value']:.1f} min")
            
            if second:
                gap = lam - second['value']
                st.info(f"Marge avant basculement vers **{second['name']}** : {gap:.1f} min")
            
            # 3. Tableau de sensibilité
            st.markdown("---")
            st.subheader("Impact des leviers")
            
            sensitivity = compute_sensitivity_table(params, info, max_delta=5)
            
            chart_labels = []
            chart_gains = []
            chart_colors = []
            
            for row in sensitivity['rows']:
                label = f"{row['lever']} −{row['delta']}min"
                chart_labels.append(label)
                chart_gains.append(row['gain_total'])
                chart_colors.append('#C00000' if row['breakpoint'] else '#4472C4')
            
            # Ajouter les pauses comme leviers secondaires
            for row in sensitivity['pause_levers']:
                if row['delta'] <= 3:  # limiter l'affichage
                    label = f"{row['lever']} −{row['delta']}min (fixe)"
                    chart_labels.append(label)
                    chart_gains.append(row['gain_total'])
                    chart_colors.append('#888888')
            
            if chart_labels:
                from matplotlib.patches import Patch
                fig_opt, ax_opt = plt.subplots(figsize=(10, max(3, len(chart_labels) * 0.35)))
                
                y_pos = range(len(chart_labels))
                ax_opt.barh(y_pos, chart_gains, color=chart_colors)
                ax_opt.set_yticks(y_pos)
                ax_opt.set_yticklabels(chart_labels, fontsize=9)
                ax_opt.set_xlabel('Gain total (minutes)')
                ax_opt.set_title(f'Gain sur la durée totale ({Q} cavaliers)')
                ax_opt.grid(True, axis='x', alpha=0.3)
                ax_opt.invert_yaxis()
                
                for i, g in enumerate(chart_gains):
                    ax_opt.text(g + 0.3, i, f'{g:.0f} min', va='center', fontsize=9, fontweight='bold')
                
                legend_elements = [
                    Patch(facecolor='#4472C4', label='Levier primaire (λ)'),
                    Patch(facecolor='#C00000', label='Breakpoint (goulot bascule)'),
                    Patch(facecolor='#888888', label='Levier secondaire (pauses, gain fixe)'),
                ]
                ax_opt.legend(handles=legend_elements, loc='lower right', fontsize=8)
                
                st.pyplot(fig_opt)
