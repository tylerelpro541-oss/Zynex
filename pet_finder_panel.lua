-- PET Finder - Zynex
-- Panel visual para Roblox

local Players = game:GetService("Players")
local player = Players.LocalPlayer

local gui = Instance.new("ScreenGui")
gui.Name = "PETFinder"
gui.ResetOnSpawn = false

local frame = Instance.new("Frame")
frame.Name = "MainPanel"
frame.Size = UDim2.new(0, 300, 0, 220)
frame.Position = UDim2.new(0.5, -150, 0.5, -110)
frame.BackgroundColor3 = Color3.fromRGB(15, 15, 20)
frame.BorderSizePixel = 0
frame.Active = true
frame.Draggable = true
frame.Parent = gui

local corner = Instance.new("UICorner")
corner.CornerRadius = UDim.new(0, 12)
corner.Parent = frame

local title = Instance.new("TextLabel")
title.Size = UDim2.new(1, -20, 0, 40)
title.Position = UDim2.new(0, 10, 0, 5)
title.BackgroundTransparency = 1
title.Text = "PET FINDER"
title.TextColor3 = Color3.fromRGB(255, 70, 170)
title.TextScaled = true
title.Font = Enum.Font.GothamBold
title.Parent = frame

local status = Instance.new("TextLabel")
status.Size = UDim2.new(1, -20, 0, 45)
status.Position = UDim2.new(0, 10, 0, 50)
status.BackgroundTransparency = 1
status.Text = "Zynex conectado visualmente"
status.TextColor3 = Color3.fromRGB(230, 230, 230)
status.TextWrapped = true
status.TextScaled = true
status.Parent = frame

local rarity = Instance.new("TextLabel")
rarity.Size = UDim2.new(1, -20, 0, 30)
rarity.Position = UDim2.new(0, 10, 0, 100)
rarity.BackgroundColor3 = Color3.fromRGB(40, 20, 35)
rarity.Text = "Filtro: ALL"
rarity.TextColor3 = Color3.fromRGB(255, 100, 190)
rarity.TextScaled = true
rarity.Parent = frame

local button = Instance.new("TextButton")
button.Size = UDim2.new(1, -20, 0, 40)
button.Position = UDim2.new(0, 10, 0, 150)
button.BackgroundColor3 = Color3.fromRGB(210, 40, 130)
button.Text = "BUSCAR HUEVOS"
button.TextColor3 = Color3.fromRGB(255, 255, 255)
button.TextScaled = true
button.Font = Enum.Font.GothamBold
button.Parent = frame

button.MouseButton1Click:Connect(function()
status.Text = "El panel funciona, pero falta conectar datos reales."
end)

gui.Parent = player:WaitForChild("PlayerGui")
