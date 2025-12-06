import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

# ==========================================
# 1. LOGIQUE DE CALCUL 
# ==========================================

def verifier_conflit_individuel(candidat_start, schedule_existant, params):
    """Vérifie les conflits selon les paramètres (identique script précédent)"""
    d_dressage = timedelta(minutes=params['d_dressage'])
    d_cross = timedelta(minutes=params['d_cross'])
    d_saut = timedelta(minutes=params['d_saut'])
    
    offset_cross = d_dressage + timedelta(minutes=params['d_pause1'])
    offset_saut = offset_cross + d_cross + timedelta(minutes=params['d_pause2'])

    c_dress_start = candidat_start
    c_dress_end = c_dress_start + d_dressage
    c_cross_start = c_dress_end + timedelta(minutes=params['d_pause1'])
    c_cross_end = c_cross_start + d_cross
    c_saut_start = c_cross_end + timedelta(minutes=params['d_pause2'])
    c_saut_end = c_saut_start + d_saut

    if schedule_existant:
        prev = schedule_existant[-1]
        if c_dress_start < prev['dressage'][1] + timedelta(minutes=params['reset_dressage']): return False
        if c_cross_start < prev['cross'][1] + timedelta(minutes=params['reset_cross']): return False
        if c_saut_start < prev['saut'][1] + timedelta(minutes=params['reset_saut']): return False

    if params['shared_arena']:
        buffer = timedelta(minutes=params['transition_shared'])
        for other in schedule_existant:
            other_saut_start, other_saut_end = other['saut']
            if (c_dress_start < other_saut_end + buffer) and (c_dress_end > other_saut_start - buffer): return False
            other_dress_start, other_dress_end = other['dressage']
            if (c_saut_start < other_dress_end + buffer) and (c_saut_end > other_dress_start - buffer): return False
                
    return True

def calculer_planning(params):
    try:
        start_time_global = datetime.strptime(params['start_time'], "%H:%M")
    except ValueError:
        st.error("Format d'heure invalide.")
        return []

    d_dressage = timedelta(minutes=params['d_dressage'])
    d_pause1 = timedelta(minutes=params['d_pause1'])
    d_cross = timedelta(minutes=params['d_cross'])
    d_pause2 = timedelta(minutes=params['d_pause2'])
    d_saut = timedelta(minutes=params['d_saut'])
    nb_cavaliers = params['nb_cavaliers']
    schedule = []

    if params['mode'] == 'Manuel':
        try:
            raw_intervals = params['manual_list'].replace(' ', '').split(',')
            intervals = [float(x) for x in raw_intervals if x]
        except ValueError:
            st.error("Erreur dans la liste manuelle.")
            return []
        
        if intervals:
            while len(intervals) < nb_cavaliers: intervals.append(intervals[-1])
        else: intervals = [5] * nb_cavaliers
            
        current_start = start_time_global
        for i in range(nb_cavaliers):
            fin_dress = current_start + d_dressage
            deb_cross = fin_dress + d_pause1
            fin_cross = deb_cross + d_cross
            deb_saut = fin_cross + d_pause2
            fin_saut = deb_saut + d_saut
            schedule.append({'id': i+1, 'dressage': (current_start, fin_dress), 'cross': (deb_cross, fin_cross), 'saut': (deb_saut, fin_saut)})
            if i < len(intervals): current_start += timedelta(minutes=intervals[i])
        return schedule

    else: # MODE AUTO
        current_search_time = start_time_global
        step = timedelta(seconds=30)
        
        progress_bar = st.progress(0)
        
        for i in range(nb_cavaliers):
            start_candidate = schedule[-1]['dressage'][0] + timedelta(minutes=1) if i > 0 else start_time_global
            
            while True:
                if verifier_conflit_individuel(start_candidate, schedule, params): break
                start_candidate += step
                if (start_candidate - start_time_global).total_seconds() > 43200: # 12h max
                    st.error("Impossible de trouver une solution (trop de contraintes).")
                    return []

            fin_dress = start_candidate + d_dressage
            deb_cross = fin_dress + d_pause1
            fin_cross = deb_cross + d_cross
            deb_saut = fin_cross + d_pause2
            fin_saut = deb_saut + d_saut
            schedule.append({'id': i+1, 'dressage': (start_candidate, fin_dress), 'cross': (deb_cross, fin_cross), 'saut': (deb_saut, fin_saut)})
            
            progress_bar.progress((i + 1) / nb_cavaliers)
            
        return schedule

# ==========================================
# 2. INTERFACE WEB (STREAMLIT)
# ==========================================

st.set_page_config(page_title="Planning CCE", layout="wide")

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
    mode = st.radio("Méthode :", ["Manuel", "Optimisation Auto"])

    manual_list = ""
    reset_dressage, reset_cross, reset_saut = 0.0, 0.0, 0.0
    shared_arena, transition_shared = False, 0.0

    if mode == "Manuel":
        manual_list = st.text_input("Liste des écarts (ex: 6, 7, 4)", "6, 7, 4")
    else:
        st.info("Temps de remise en état (Reset) entre 2 cavaliers :")
        col1, col2, col3 = st.columns(3)
        with col1: reset_dressage = st.number_input("Reset Dress.", value=1.0)
        with col2: reset_cross = st.number_input("Reset Cross", value=2.0)
        with col3: reset_saut = st.number_input("Reset Saut", value=1.5)
        
        shared_arena = st.checkbox("Même terrain (Dressage / Saut)")
        if shared_arena:
            transition_shared = st.number_input("Temps transition D/S", value=5.0)

    generate_btn = st.button("Générer le Planning", type="primary")

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

    schedule = calculer_planning(params)

    if schedule:
        # Affichage du graphe
        fig, ax = plt.subplots(figsize=(12, nb_cavaliers * 0.5 + 2)) # Hauteur dynamique
        colors = {'dressage': '#4472C4', 'cross': '#548235', 'saut': '#C00000'}
        bar_height = 0.5
        
        for cav in schedule:
            y = cav['id']
            # Dressage
            start, end = mdates.date2num(cav['dressage'][0]), mdates.date2num(cav['dressage'][1])
            ax.barh(y, end - start, left=start, height=bar_height, color=colors['dressage'], edgecolor='white')
            ax.text(start, y + 0.35, cav['dressage'][0].strftime("%H:%M"), fontsize=8, ha='center', fontweight='bold')
            # Cross
            start, end = mdates.date2num(cav['cross'][0]), mdates.date2num(cav['cross'][1])
            ax.barh(y, end - start, left=start, height=bar_height, color=colors['cross'], edgecolor='white')
            ax.text(start, y + 0.35, cav['cross'][0].strftime("%H:%M"), fontsize=8, ha='center', fontweight='bold')
            # Saut
            start, end = mdates.date2num(cav['saut'][0]), mdates.date2num(cav['saut'][1])
            ax.barh(y, end - start, left=start, height=bar_height, color=colors['saut'], edgecolor='white')
            ax.text(start, y + 0.35, cav['saut'][0].strftime("%H:%M"), fontsize=8, ha='center', fontweight='bold')

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
