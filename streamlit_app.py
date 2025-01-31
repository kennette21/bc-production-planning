import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import date
import json
import copy
import random
from forecast_page import forecast_page
from compliance_page import compliance_page


# Define pages using a list or grouped structure
pages = [
    st.Page(forecast_page, title="Production Planning"),
    st.Page(compliance_page, title="Compliance"),
]

pg = st.navigation(pages)
pg.run()

# Footer
st.write("Developed by BrainCoral Dev Team.")