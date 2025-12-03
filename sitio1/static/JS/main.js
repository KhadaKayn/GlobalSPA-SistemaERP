const menu = document.getElementById('menu');
const sidebar = document.getElementById('sidebar');
const main= document.getElementById('main')

menu.addEventListener('click',()=>{
  sidebar.classList.toggle('menu-toggle')
  main.classList.toggle('menu-toggle')
})


  // Mostrar/ocultar menú al hacer clic en la imagen
  document.addEventListener('DOMContentLoaded', function() {
    const perfilImg = document.getElementById('perfil-img');
    const menu = document.getElementById('menu-desplegable');

    perfilImg.addEventListener('click', function() {
      menu.style.display = menu.style.display === 'block' ? 'none' : 'block';
    });

    // Ocultar el menú si se hace clic fuera
    document.addEventListener('click', function(e) {
      if (!perfilImg.contains(e.target) && !menu.contains(e.target)) {
        menu.style.display = 'none';
      }
    });
  });
