# The RMF Industrial Project

<p>
  <img
    src="docs/imgs/rmf2-ue-warehouse-demo.png"
    alt="rmf2-ue-warehouse-demo"
    height="180"
  />
  <img
    src="https://github.com/ros-industrial/res_mapf/blob/main/docs/assets/demo.gif?raw=true"
    alt="rmf2-mapf-pybullet-demo"
    height="180"
  />
  <img
    src="https://github.com/ros-industrial/rmf2-ui/blob/main/docs/imgs/desktop-light-schedule.png?raw=true"
    alt="rmf2-ui-desktop-light-schedule"
    height="180"
  />
</p>

The RMF Industrial project provides RMF services for Manufacturing and Logistics.


## Summary

The RMF Industrial project tries to adopt the new [Next Gen RMF interfaces](https://github.com/open-rmf/next_gen_prototype)
and provides a suite of open source modules for industrial users
to build planning, scheduling and orchestration in large-scale simulated facility,
showcasing RMF’s flexibility, scalability in multi-robot coordination.

## Documentation

The hosted documentation is available at <https://dev.rmf-industrial.org/latest>.

## RMF Industrial Modules

| Module Name | Repositories |
| - | - |
| RMF Industrial | <https://github.com/ros-industrial/rmf_industrial> |
| Documentation | <https://github.com/ros-industrial/rmf2-docs> |
| VDA5050 Library and support tools | <https://github.com/ros-industrial/vda5050_core><br> <https://github.com/ros-industrial/vda5050_interfaces> |
| Unreal Engine Plugins | <https://github.com/ros-industrial/rmf2-unreal> |
| MAPF Robot Execution System (RES) | <https://github.com/ros-industrial/res_mapf> |
| Task Orchestrator | <https://github.com/ros-industrial/rmf2_task_orchestrator> |
| Task Scheduler | <https://github.com/ros-industrial/rmf2_scheduler> |
| Web UI | <https://github.com/ros-industrial/rmf2-ui> |



## Demonstrations

<table>
  <thead>
    <tr>
      <th>
        <img
          src="docs/imgs/rmf2-ue-warehouse-demo.png"
          alt="rmf2-ue-warehouse-demo"
          height="300"
        />
      </th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>
        <p align="center">
          Warehouse Demonstration
          (<a href="https://downloads.rmf-industrial.org/UE5Demos/RMF2_SIM_20260611.zip">Download Link</a>)
        </p>
      </td>
    </tr>
  </tbody>
</table>

### Warehouse Simulation Setup

Download the latest simulation

```sh
# For RMF-I 0.2.0:
curl -OL https://downloads.rmf-industrial.org/UE5Demos/RMF2_SIM_0.2.0.zip

# For RMF-I Legacy:
curl -OL https://downloads.rmf-industrial.org/UE5Demos/RMF2_SIM_20260611.zip
```

Unzip the simulation

```sh
# For RMF-I 0.2.0:
unzip RMF2_SIM_0.2.0.zip
cd ./RMF2_SIM_0.2.0

# For RMF-I Legacy:
unzip RMF2_SIM_20260611.zip
cd ./RMF2_SIM_20260611
```

Start the simulation
```sh
# For RMF-I 0.2.0:
./RMF2_SIM.sh

# For RMF-I Legacy:
./Linux/RMF2_SIM.sh
```

The simulation should start full screen matching your screen resolution.
You can press `Alt + Enter` to toggle between fullscreen and windowed mode.

You can also start the simulation in a windowed mode with specific resolution
```sh
# For RMF-I 0.2.0:
./RMF2_SIM.sh -windowed -resx 1920 -resy 1080

# For RMF-I Legacy:
./Linux/RMF2_SIM.sh -windowed -resx 1920 -resy 1080
```

The simulation controls are similar to a typical game.
Here are the basics
- Movement: Keyboard `W A S D` or Controller Left Stick
  - `W`, `S` move forward and backward
  - `A`, `D` pan left and right
  - `Q`, `E` move up and down
- View: Mouse  or Controller Right Stick
  - click on the screen and hold to move around

Other controls
- Tab `M` to show Map marker
